// Per-process diagnostic for waits on the concrete Metal command-buffer class.
// Install before timing and count after a separately verified MPS
// synchronization.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/runtime.h>
#include <stdatomic.h>
#include <stdint.h>

static _Atomic uint64_t waits;
static void (*previous)(id, SEL);

static void measured_wait(id buffer, SEL selector) {
  atomic_fetch_add_explicit(&waits, 1, memory_order_relaxed);
  previous(buffer, selector);
}

int install_wait_counter(void) {
  @autoreleasepool {
    if (previous)
      return 1;
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    id<MTLCommandQueue> queue = [device newCommandQueue];
    id<MTLCommandBuffer> buffer = [queue commandBuffer];
    Class cls = object_getClass(buffer);
    SEL sel = @selector(waitUntilCompleted);
    Method method = class_getInstanceMethod(cls, sel);
    if (!method)
      return 0;
    previous = (void (*)(id, SEL))method_getImplementation(method);
    class_replaceMethod(cls, sel, (IMP)measured_wait,
                        method_getTypeEncoding(method));
    return 1;
  }
}

uint64_t command_buffer_waits(void) {
  return atomic_load_explicit(&waits, memory_order_relaxed);
}
