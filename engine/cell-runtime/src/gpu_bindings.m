#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>

@interface CellBindings : NSObject {
@public
    id<MTLDevice> device;
    id<MTLComputePipelineState> pipeline;
    id<MTLCommandQueue> queue;
    id<MTLBuffer> buffers[6];
}
@end
@implementation CellBindings
@end

void *cell_gpu_open(const char *source) {
    @autoreleasepool {
        CellBindings *s = [CellBindings new];
        s->device = MTLCreateSystemDefaultDevice();
        if (!s->device) return NULL;
        NSError *error = nil;
        id<MTLLibrary> lib = [s->device newLibraryWithSource:[NSString stringWithUTF8String:source]
                                                      options:nil error:&error];
        if (lib) s->pipeline = [s->device newComputePipelineStateWithFunction:[lib newFunctionWithName:@"bindings"] error:&error];
        s->queue = [s->device newCommandQueue];
        if (!s->pipeline || !s->queue) { NSLog(@"Cell Metal initialization: %@",error); return NULL; }
        return (__bridge_retained void *)s;
    }
}
void cell_gpu_close(void *ptr) { @autoreleasepool { (void)CFBridgingRelease(ptr); } }

static bool reserve(CellBindings *s, int i, size_t bytes) {
    bytes = MAX(4, bytes);
    if (!s->buffers[i] || s->buffers[i].length < bytes)
        s->buffers[i] = [s->device newBufferWithLength:bytes options:MTLResourceStorageModeShared];
    return s->buffers[i] != nil;
}

// The Rust caller owns immutable input slices for this synchronous call.
// The device emits two positions per accepted binding in a shared output bank.
int cell_gpu_match(void *ptr, const int *left, size_t nl, const int *right, size_t nr,
                   const int *tests, size_t nt, const int *shape, int width, int *out, double *gpu) {
    @autoreleasepool {
        CellBindings *s = (__bridge CellBindings *)ptr;
        size_t bytes[6] = {4*nl,4*nr,4*nt,24,4,8*(size_t)width};
        for (int i=0;i<6;i++) if (!reserve(s,i,bytes[i])) return -1;
        const void *input[] = {left,right,tests,shape};
        for (int i=0;i<4;i++) if (bytes[i]) memcpy(s->buffers[i].contents,input[i],bytes[i]);
        *(uint32_t *)s->buffers[4].contents = 0;
        id<MTLCommandBuffer> command = [s->queue commandBuffer];
        id<MTLComputeCommandEncoder> enc = [command computeCommandEncoder];
        if (!enc) return -1;
        [enc setComputePipelineState:s->pipeline];
        for (int i=0;i<6;i++) [enc setBuffer:s->buffers[i] offset:0 atIndex:i];
        NSUInteger group = MIN(s->pipeline.maxTotalThreadsPerThreadgroup,128);
        [enc dispatchThreads:MTLSizeMake(width,1,1) threadsPerThreadgroup:MTLSizeMake(group,1,1)];
        [enc endEncoding]; [command commit]; [command waitUntilCompleted];
        if (command.status != MTLCommandBufferStatusCompleted) { NSLog(@"Cell GPU: %@",command.error); return -1; }
        uint32_t count = *(uint32_t *)s->buffers[4].contents;
        if (count > (uint32_t)width) return -1;
        memcpy(out,s->buffers[5].contents,8*(size_t)count);
        *gpu = command.GPUEndTime-command.GPUStartTime;
        return (int)count;
    }
}

// Persistent per-table Cell port banks, shared across all rule consumers.
@interface CellParentPorts : NSObject {
@public
    id<MTLDevice> device;
    id<MTLComputePipelineState> pipeline;
    id<MTLCommandQueue> queue;
    id<MTLBuffer> weights, output;
    NSMutableDictionary<NSNumber *,id<MTLBuffer>> *banks;
}
@end
@implementation CellParentPorts
@end

void *cell_ports_open(const char *source, const float *weights, size_t n) {
    @autoreleasepool {
        CellParentPorts *s=[CellParentPorts new];
        s->device=MTLCreateSystemDefaultDevice();
        NSError *error=nil;
        id<MTLLibrary> lib=[s->device newLibraryWithSource:[NSString stringWithUTF8String:source] options:nil error:&error];
        if (lib) s->pipeline=[s->device newComputePipelineStateWithFunction:[lib newFunctionWithName:@"propose_parent"] error:&error];
        if (!s->pipeline) { NSLog(@"parent pipeline: %@",error); return NULL; }
        s->queue=[s->device newCommandQueue];
        s->weights=[s->device newBufferWithBytes:weights length:4*n options:MTLResourceStorageModeShared];
        s->banks=[NSMutableDictionary new];
        return s->weights && s->queue ? (__bridge_retained void *)s : NULL;
    }
}
int cell_ports_patch(void *ptr, int table, int width, int capacity, const int *slots, const int *rows, int n) {
    @autoreleasepool {
        CellParentPorts *s=(__bridge CellParentPorts *)ptr;
        id<MTLBuffer> b=s->banks[@(table)];
        size_t need=MAX((size_t)4,4*(size_t)width*capacity);
        if (!b || b.length<need) {
            id<MTLBuffer> next=[s->device newBufferWithLength:MAX(need,b.length*2) options:MTLResourceStorageModeShared];
            if (!next) return -1;
            if (b) memcpy(next.contents,b.contents,b.length);
            s->banks[@(table)]=b=next;
        }
        for (int i=0;i<n;i++) memcpy((int *)b.contents+(size_t)width*slots[i],rows+(size_t)width*i,4*width);
        return 0;
    }
}
// All source rules in this call read the same frozen graph epoch. One fence.
int cell_ports_predict(void *ptr, const int *desc, int groups, const int *cols, int count, int *out, double *gpu) {
    @autoreleasepool {
        CellParentPorts *s=(__bridge CellParentPorts *)ptr;
        if (!count) { *gpu=0; return 0; }
        size_t bytes=(size_t)count*4;
        if (s->output.length<bytes) s->output=[s->device newBufferWithLength:bytes options:MTLResourceStorageModeShared];
        if (!s->output) return -1;
        id<MTLCommandBuffer> cmd=[s->queue commandBuffer];
        id<MTLComputeCommandEncoder> enc=[cmd computeCommandEncoder];
        if (!enc) return -1;
        [enc setComputePipelineState:s->pipeline];
        [enc setBuffer:s->weights offset:0 atIndex:4];
        int base=0;
        for (int g=0;g<groups;g++) {
            const int *d=desc+8*g;
            if (!d[2]) continue;
            [enc setBuffer:s->banks[@(d[0])] offset:0 atIndex:0];
            [enc setBuffer:s->banks[@(d[1])] offset:0 atIndex:1];
            [enc setBytes:d+3 length:16 atIndex:2];
            [enc setBytes:cols+d[7] length:d[6]*4 atIndex:3];
            [enc setBuffer:s->output offset:base*4 atIndex:5];
            [enc dispatchThreads:MTLSizeMake(d[2],1,1) threadsPerThreadgroup:MTLSizeMake(MIN(128,s->pipeline.maxTotalThreadsPerThreadgroup),1,1)];
            base+=d[2];
        }
        [enc endEncoding]; [cmd commit]; [cmd waitUntilCompleted];
        if (cmd.status!=MTLCommandBufferStatusCompleted) return -1;
        memcpy(out,s->output.contents,bytes);
        *gpu=cmd.GPUEndTime-cmd.GPUStartTime;
        return 0;
    }
}
