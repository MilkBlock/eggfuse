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
