import Foundation
import Metal

func require(_ ok: Bool, _ message: String) throws {
    if !ok { throw NSError(domain: message, code: 1) }
}
func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }
let args = CommandLine.arguments
try require(args.count == 4, "runner bundle.json kernels.metal report.json")
let bundleURL = URL(fileURLWithPath: args[1])
let base = bundleURL.deletingLastPathComponent()
let bundle = try JSONSerialization.jsonObject(with: Data(contentsOf: bundleURL)) as! [String: Any]
let device: MTLDevice = {
    guard let d = MTLCreateSystemDefaultDevice() else { fatalError("Metal unavailable") }
    return d
}()
let queue = device.makeCommandQueue()!
let options = MTLCompileOptions()
if #available(macOS 15.0, *) { options.mathMode = .safe }
let library = try device.makeLibrary(source: String(contentsOfFile: args[2], encoding: .utf8), options: options)
var pipelines: [String: MTLComputePipelineState] = [:]
for name in ["boolean_mm", "pair_columns", "intersect", "merge_columns"] {
    pipelines[name] = try device.makeComputePipelineState(function: library.makeFunction(name: name)!)
}
final class Lane {
    let spec: [String: Any]
    var buffers: [String: MTLBuffer] = [:]
    var gpu: [Double] = [], wall: [Double] = []
    var returnGPU: [Double] = [], returnWall: [Double] = []
    var unionGPU: [Double] = [], unionWall: [Double] = []
    var readbacks: [String: MTLBuffer] = [:]
    var allocationBytes = 0, uploadBytes = 0
    var setupSeconds = 0.0
    init(_ spec: [String: Any]) throws {
        self.spec = spec
        let start = now(), cb = queue.makeCommandBuffer()!, blit = cb.makeBlitCommandEncoder()!
        for desc in spec["buffers"] as! [[String: Any]] {
            let name = desc["name"] as! String, bytes = desc["bytes"] as! Int
            guard let b = device.makeBuffer(length: max(4, bytes), options: .storageModePrivate) else {
                throw NSError(domain: "GPU allocation", code: 1)
            }
            b.label = name; buffers[name] = b; allocationBytes += b.length
            if let path = desc["file"] as? String {
                let data = try Data(contentsOf: base.appendingPathComponent(path))
                try require(data.count == bytes, "input byte count")
                let staging = data.withUnsafeBytes { device.makeBuffer(bytes: $0.baseAddress!, length: bytes, options: .storageModeShared)! }
                blit.copy(from: staging, sourceOffset: 0, to: b, destinationOffset: 0, size: bytes)
                uploadBytes += bytes
            } else { blit.fill(buffer: b, range: 0..<b.length, value: 0) }
        }
        blit.endEncoding(); cb.commit(); cb.waitUntilCompleted()
        try require(cb.status == .completed, cb.error?.localizedDescription ?? "upload failed")
        for name in spec["outputs"] as! [String] {
            readbacks[name] = device.makeBuffer(length: buffers[name]!.length, options: .storageModeShared)!
        }
        setupSeconds = now() - start
    }
    func encode(_ cb: MTLCommandBuffer, unionOnly: Bool = false) {
        let reset = cb.makeBlitCommandEncoder()!
        for pair in spec["reset"] as! [[String]] {
            let src = buffers[pair[0]]!, dst = buffers[pair[1]]!
            reset.copy(from: src, sourceOffset: 0, to: dst, destinationOffset: 0, size: src.length)
        }
        reset.endEncoding()
        for op in spec["ops"] as! [[String: Any]] {
            let name = op["kernel"] as! String
            if unionOnly && name != "merge_columns" { continue }
            let enc = cb.makeComputeCommandEncoder()!, pipe = pipelines[name]!
            enc.setComputePipelineState(pipe)
            let names = op["buffers"] as! [String]
            for (i, name) in names.enumerated() { enc.setBuffer(buffers[name]!, offset: 0, index: i) }
            let config = (op["args"] as! [Int]).map { UInt32($0) }
            config.withUnsafeBytes { enc.setBytes($0.baseAddress!, length: $0.count, index: names.count) }
            let count = op["count"] as! Int, threads = op["threads"] as! Int
            if op["groups"] as! Bool {
                enc.dispatchThreadgroups(MTLSize(width: count, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
            } else {
                enc.dispatchThreads(MTLSize(width: count, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
            }
            enc.endEncoding()
        }
    }
    func copyOutputs(_ cb: MTLCommandBuffer) {
        let enc = cb.makeBlitCommandEncoder()!
        for name in spec["outputs"] as! [String] {
            let src = buffers[name]!
            enc.copy(from: src, sourceOffset: 0, to: readbacks[name]!, destinationOffset: 0, size: src.length)
        }
        enc.endEncoding()
    }
    func run(unionOnly: Bool = false, returningOutputs: Bool = false) throws -> (Double, Double) {
        let start = now(), cb = queue.makeCommandBuffer()!
        encode(cb, unionOnly: unionOnly)
        if returningOutputs { copyOutputs(cb) }
        cb.commit(); cb.waitUntilCompleted()
        try require(cb.status == .completed, cb.error?.localizedDescription ?? "execution failed")
        return (cb.gpuEndTime - cb.gpuStartTime, now() - start)
    }
    func export() throws -> Double {
        // Separate explicit final materialization/readback cost; no intermediate
        // GPU state is read by the host to decide which computation to execute.
        let start = now(), cb = queue.makeCommandBuffer()!
        copyOutputs(cb); cb.commit(); cb.waitUntilCompleted()
        try require(cb.status == .completed, "readback failed")
        let elapsed = now() - start
        for (name, buffer) in readbacks {
            let path = "\(spec["name"] as! String)-\(name).f16"
            try Data(bytes: buffer.contents(), count: buffer.length).write(to: base.appendingPathComponent(path))
        }
        return elapsed
    }
}
let specs = bundle["lanes"] as! [[String: Any]]
let repeats = bundle["repeats"] as! Int
var reports: [[String: Any]] = []
for caseName in bundle["cases"] as! [String] {
    let lanes = try specs.filter { ($0["case"] as! String) == caseName }.map { try Lane($0) }
    for lane in lanes { for _ in 0..<2 { _ = try lane.run() } }
    for round in 0..<repeats {
        var order = Array(lanes.indices)
        if round % 2 == 1 { order.reverse() }
        let shift = round % lanes.count
        order = Array(order[shift...] + order[..<shift])
        for i in order {
            let (gpu, wall) = try lanes[i].run()
            lanes[i].gpu.append(gpu); lanes[i].wall.append(wall)
        }
    }
    for round in 0..<repeats {
        let order = round % 2 == 0 ? Array(lanes.indices) : Array(lanes.indices.reversed())
        for i in order {
            let (gpu, wall) = try lanes[i].run(returningOutputs: true)
            lanes[i].returnGPU.append(gpu); lanes[i].returnWall.append(wall)
        }
    }
    for lane in lanes {
        // Last full execution still owns the final outputs.
        let readback = try lane.export()
        for _ in 0..<3 {
            let (gpu, wall) = try lane.run(unionOnly: true)
            lane.unionGPU.append(gpu); lane.unionWall.append(wall)
        }
        reports.append(["name": lane.spec["name"]!, "case": caseName,
                        "mode": lane.spec["mode"]!, "gpu_seconds": lane.gpu,
                        "submit_wait_seconds": lane.wall, "reset_union_gpu_seconds": lane.unionGPU,
                        "with_output_readback_gpu_seconds": lane.returnGPU,
                        "with_output_readback_submit_wait_seconds": lane.returnWall,
                        "reset_union_submit_wait_seconds": lane.unionWall,
                        "initial_upload_allocation_seconds": lane.setupSeconds,
                        "final_readback_seconds": readback, "allocated_gpu_bytes": lane.allocationBytes,
                        "output_readback_shared_bytes": lane.readbacks.values.reduce(0) { $0 + $1.length },
                        "initial_upload_bytes": lane.uploadBytes])
    }
}
let result: [String: Any] = ["device": device.name, "os": ProcessInfo.processInfo.operatingSystemVersionString,
    "scope": "standalone bounded relational Cell prototype", "lanes": reports,
    "gpu_execution": true, "runtime_takeover": false, "repeats": repeats]
try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: args[3]))
print("Completed \(reports.count) GPU lanes on \(device.name)")
