// Count Metal compute dispatch API calls in this benchmark process only.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/runtime.h>
#include <stdatomic.h>

static atomic_ulong dispatches;
static _Thread_local unsigned nesting;

static void countDirect(Class cls, SEL sel) {
    Method method = class_getInstanceMethod(cls, sel);
    if (!method) return;
    typedef void (*Fn)(id, SEL, MTLSize, MTLSize);
    Fn original = (Fn)method_getImplementation(method);
    IMP wrapped = imp_implementationWithBlock(^(id obj, MTLSize grid, MTLSize group) {
        if (!nesting++) atomic_fetch_add(&dispatches, 1);
        original(obj, sel, grid, group);
        nesting--;
    });
    class_replaceMethod(cls, sel, wrapped, method_getTypeEncoding(method));
}

int install_dispatch_counter(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        id<MTLCommandQueue> queue = [device newCommandQueue];
        id<MTLCommandBuffer> buffer = [queue commandBuffer];
        id<MTLComputeCommandEncoder> enc = [buffer computeCommandEncoder];
        if (!enc) return 0;
        Class cls = object_getClass(enc);
        countDirect(cls, @selector(dispatchThreads:threadsPerThreadgroup:));
        countDirect(cls, @selector(dispatchThreadgroups:threadsPerThreadgroup:));
        [enc endEncoding];
        return 1;
    }
}

unsigned long count_dispatches(void) { return atomic_load(&dispatches); }
