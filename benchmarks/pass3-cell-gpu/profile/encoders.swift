// Standalone timing adapter for the PyTorch/Metal Pass 3 executor.
// Accepts only device state captured after ingress, before the first source Run.
import Foundation
import Metal

struct BufferSpec: Decodable { let bytes: Int; let shape: [Int]; let itemsize: Int }
struct Layout: Decodable { let buffers: [String:BufferSpec]; let threads, steps, lanes: Int }
struct Sample: Encodable { let run: Int; let name: String; let start,end: UInt64; let ns: UInt64 }
struct Command: Encodable { let first,last: Int; let gpuMS: Double }
struct Output: Encodable { let samples: [Sample]; let commands: [Command]; let wallMS: Double; let completed: Int; let device: String; let mode: String }
struct Failure: Error { let reason: String; init(_ s:String){reason=s} }

func profile(_ src: URL, _ dst: URL, _ mode: String) throws {
    let fm=FileManager.default
    try fm.createDirectory(at:dst,withIntermediateDirectories:true)
    let cfg=try JSONDecoder().decode(Layout.self,from:Data(contentsOf:src.appendingPathComponent("layout.json")))
    guard let gpu=MTLCreateSystemDefaultDevice(), let queue=gpu.makeCommandQueue(),
          gpu.supportsCounterSampling(.atStageBoundary),
          let timestamps=gpu.counterSets?.first(where:{$0.name==MTLCommonCounterSet.timestamp.rawValue}) else {
        throw Failure("stage-boundary timestamp sampling unavailable")
    }
    let shader=try String(contentsOf:src.appendingPathComponent("profile.metal"),encoding:.utf8)
    let extra="""
    kernel void clear_counts(device int *counts,uint i [[thread_position_in_grid]]){counts[i]=0;}
    """
    let lib=try gpu.makeLibrary(source:shader+"\n"+extra,options:nil)
    var buffers=[String:MTLBuffer]()
    for (name,spec) in cfg.buffers {
        guard let buf=gpu.makeBuffer(length:spec.bytes,options:.storageModeShared) else {throw Failure("buffer allocation")}
        buf.label=name
        let file=src.appendingPathComponent(name+".bin")
        if fm.fileExists(atPath:file.path) {
            let data=try Data(contentsOf:file);guard data.count==spec.bytes else{throw Failure("short "+name)}
            _=data.withUnsafeBytes{memcpy(buf.contents(),$0.baseAddress!,spec.bytes)}
        } else {memset(buf.contents(),0,spec.bytes)}
        buffers[name]=buf
    }
    let nrules=cfg.buffers["wm"]!.shape[0], countWords=cfg.buffers["count"]!.bytes/4
    func constant(_ name:String) throws -> Int {
        let prefix="#define "+name+" "
        guard let line=shader.split(separator:"\n").first(where:{$0.hasPrefix(prefix)}),
              let value=Int(line.dropFirst(prefix.count)) else{throw Failure("missing shader constant "+name)}
        return value
    }
    let traceCap=try constant("TRACE_CAP"), tokenCap=try constant("TOKEN_CAP"), depth=try constant("DEPTH")
    for (name,words) in [("scratch",nrules*513+3+traceCap*5),("certs",nrules*2*tokenCap*(depth+3))]{
        buffers[name]=gpu.makeBuffer(length:words*4,options:.storageModeShared)!
        memset(buffers[name]!.contents(),0,words*4)
    }
    let names=["clear_counts","next_run","search","commit","entry_only","spine_only","entry_matches","spine_matches","emit_tokens","publish_spine","sort_unique","apply_rhs","finish_repair","export_rows"]
    var pipelines=[String:MTLComputePipelineState]()
    for n in names { pipelines[n]=try gpu.makeComputePipelineState(function:lib.makeFunction(name:n)!) }
    let search=["prog","literal","state","meta","dyn","head","wm","count","tokens","#"]
    let rhs=["prog","literal","state","meta","dyn","head","wm","count","tokens","rhs","writes","runs","resumes","#"]
    var samples=[Sample](),commands=[Command]()
    let desc=MTLCounterSampleBufferDescriptor()
    desc.counterSet=timestamps;desc.storageMode = .shared;desc.sampleCount=2*12*32
    let page=try gpu.makeCounterSampleBuffer(descriptor:desc)
    let started=ProcessInfo.processInfo.systemUptime
    for base in stride(from:0,to:cfg.steps,by:32) {
        let end=min(base+32,cfg.steps), cb=queue.makeCommandBuffer()!
        var records=[(Int,String)]()
        func dispatch(_ run:Int,_ name:String,_ args:[String],_ n:Int){
            let pd=MTLComputePassDescriptor(), index=records.count*2
            pd.sampleBufferAttachments[0].sampleBuffer=page
            pd.sampleBufferAttachments[0].startOfEncoderSampleIndex=index
            pd.sampleBufferAttachments[0].endOfEncoderSampleIndex=index+1
            let enc=cb.makeComputeCommandEncoder(descriptor:pd)!, pipeline=pipelines[name]!
            enc.label="fn="+name;enc.setComputePipelineState(pipeline)
            for (i,key) in args.enumerated(){
                if key=="#" {var lanes=Int32(cfg.lanes);enc.setBytes(&lanes,length:4,index:i)}
                else {enc.setBuffer(buffers[key]!,offset:0,index:i)}
            }
            enc.dispatchThreads(MTLSize(width:n,height:1,depth:1),
                                threadsPerThreadgroup:MTLSize(width:min(n,pipeline.maxTotalThreadsPerThreadgroup),height:1,depth:1))
            enc.endEncoding();records.append((run,name))
        }
        for i in base..<end {
            let r=i+1
            dispatch(r,"clear_counts",["count"],countWords)
            dispatch(r,"next_run",["prog","state","regs","count"],1)
            if mode=="base" {
                dispatch(r,"search",search,cfg.threads);dispatch(r,"commit",rhs,1)
            } else {
                if mode=="detail" {
                    dispatch(r,"spine_matches",search+["certs"],cfg.threads)
                    dispatch(r,"entry_matches",search+["certs"],cfg.threads)
                    dispatch(r,"emit_tokens",["prog","literal","state","meta","dyn","count","tokens","certs"],cfg.threads)
                } else {
                    dispatch(r,"spine_only",search,cfg.threads);dispatch(r,"entry_only",search,cfg.threads)
                }
                dispatch(r,"sort_unique",rhs+["scratch"],1)
                dispatch(r,"apply_rhs",rhs+["scratch"],1)
                dispatch(r,"publish_spine",["prog","state","meta","scratch"],1)
                dispatch(r,"finish_repair",["prog","literal","state","meta","dyn","head","writes","runs","scratch"],1)
            }
        }
        cb.commit();cb.waitUntilCompleted()
        let first=base+1,last=end
        guard cb.status == .completed,let bytes=try page.resolveCounterRange(0..<(records.count*2)) else{throw Failure("invalid command/timestamps: "+String(describing:cb.error))}
        try bytes.withUnsafeBytes{raw in
            for (i,rec) in records.enumerated(){
                let from=raw.loadUnaligned(fromByteOffset:i*16,as:UInt64.self),to=raw.loadUnaligned(fromByteOffset:i*16+8,as:UInt64.self)
                guard from>0,to>=from,to != UInt64.max else{throw Failure("invalid counter")}
                samples.append(Sample(run:rec.0,name:rec.1,start:from,end:to,ns:to-from))
            }
        }
        commands.append(Command(first:first,last:last,gpuMS:(cb.gpuEndTime-cb.gpuStartTime)*1000))
    }
    let wall=(ProcessInfo.processInfo.systemUptime-started)*1000
    let st=buffers["state"]!.contents().assumingMemoryBound(to:Int32.self)
    guard st[5]==0,st[7]==1 else{throw Failure("graph or shadow counter mismatch")}
    let output=Output(samples:samples,commands:commands,wallMS:wall,completed:Int(st[11]),device:gpu.name,mode:mode)
    try JSONEncoder().encode(output).write(to:dst.appendingPathComponent("timing.json"))
    // Export canonical fields using exactly the production GPU exporter.
    let cols=cfg.buffers["dyn"]!.shape[1],rows=Int(st[0])
    let exported=gpu.makeBuffer(length:rows*cols*8,options:.storageModeShared)!
    memset(exported.contents(),0,exported.length)
    let cb=queue.makeCommandBuffer()!, enc=cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipelines["export_rows"]!)
    for (i,key) in ["prog","literal","state","meta","dyn"].enumerated(){enc.setBuffer(buffers[key]!,offset:0,index:i)}
    enc.setBuffer(exported,offset:0,index:5)
    enc.dispatchThreads(MTLSize(width:rows,height:1,depth:1),threadsPerThreadgroup:MTLSize(width:32,height:1,depth:1))
    enc.endEncoding();cb.commit();cb.waitUntilCompleted()
    guard cb.status == .completed else{throw Failure("export failed")}
    for (key,length) in [("state",cfg.buffers["state"]!.bytes),("rhs",Int(st[9])*cfg.buffers["rhs"]!.shape[1]*8),
                         ("writes",Int(st[10])*cfg.buffers["writes"]!.shape[1]*8),("resumes",Int(st[16])*24),
                         ("runs",Int(st[11])*24),("meta",rows*24)] {
        try Data(bytes:buffers[key]!.contents(),count:length).write(to:dst.appendingPathComponent(key+".bin"))
    }
    let cap=try constant("ROW_CAP"), symbols=try constant("NSYMBOLS")
    try Data(bytes:buffers["meta"]!.contents().advanced(by:6*cap*4),count:(symbols+rows+2)*4).write(to:dst.appendingPathComponent("parents.bin"))
    try Data(bytes:exported.contents(),count:exported.length).write(to:dst.appendingPathComponent("rows.bin"))
    print(mode,st[11],"Runs",wall,"ms")
}
let a=CommandLine.arguments
guard a.count==4,["base","split","detail"].contains(a[3]) else{fatalError("ingress output base|split|detail")}
try profile(URL(fileURLWithPath:a[1]),URL(fileURLWithPath:a[2]),a[3])
