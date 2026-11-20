#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <string.h>
@interface EFDelta:NSObject
@property(nonatomic,strong) id<MTLDevice> device;
@property(nonatomic,strong) id<MTLCommandQueue> queue;
@property(nonatomic,strong) id<MTLComputePipelineState> pipeline;
@property(nonatomic,strong) NSArray<id<MTLBuffer>>* bank;
@property(nonatomic) NSUInteger claims;
@property(nonatomic) int width;
@end
@implementation EFDelta
@end
void *ef_delta_open(const char *source,const int32_t *catalog,uint32_t claims,uint32_t ports,uint32_t rules,int32_t width){
 @autoreleasepool{
  static id<MTLDevice> device=nil;static id<MTLComputePipelineState> pipeline=nil;
  EFDelta *s=[EFDelta new];if(!device)device=MTLCreateSystemDefaultDevice();s.device=device;s.queue=[s.device newCommandQueue];
  if(!pipeline){
  NSError *error=nil;
  id<MTLLibrary> lib=[s.device newLibraryWithSource:[NSString stringWithUTF8String:source] options:nil error:&error];
  if(!lib){NSLog(@"%@",error);return NULL;}
  s.pipeline=[s.device newComputePipelineStateWithFunction:[lib newFunctionWithName:@"validate"] error:&error];
  if(!s.pipeline){NSLog(@"%@",error);return NULL;}pipeline=s.pipeline;
  }else{s.pipeline=pipeline;}
  NSUInteger sizes[5]={claims*(11+width)*4,ports*(8+width)*4,rules*4,claims*4,claims*(4+width)*4};
  NSMutableArray *banks=[NSMutableArray array];
  for(int i=0;i<5;i++){id<MTLBuffer>b=[s.device newBufferWithLength:MAX(4,sizes[i]) options:MTLResourceStorageModeShared];
   if(!b)return NULL;memset(b.contents,0,b.length);[banks addObject:b];}
  s.bank=banks;s.width=width;s.claims=claims;
  memcpy(s.bank[0].contents,catalog,sizes[0]);return (__bridge_retained void *)s;
 }
}
void *ef_delta_bank(void *p,int i){EFDelta *s=(__bridge EFDelta*)p;return s.bank[i].contents;}
int ef_delta_run(void *p,double *seconds){
 @autoreleasepool{EFDelta *s=(__bridge EFDelta*)p;
  id<MTLCommandBuffer>cb=[s.queue commandBuffer];id<MTLComputeCommandEncoder>e=[cb computeCommandEncoder];
  [e setComputePipelineState:s.pipeline];for(int i=0;i<5;i++)[e setBuffer:s.bank[i] offset:0 atIndex:i];
  int width=s.width;[e setBytes:&width length:4 atIndex:5];
  [e dispatchThreads:MTLSizeMake(s.claims,1,1) threadsPerThreadgroup:MTLSizeMake(MIN(64,s.pipeline.maxTotalThreadsPerThreadgroup),1,1)];
  [e endEncoding];[cb commit];[cb waitUntilCompleted];if(cb.status==MTLCommandBufferStatusError){NSLog(@"%@",cb.error);return 0;}
  *seconds=cb.GPUEndTime-cb.GPUStartTime;return 1;
 }
}
void ef_delta_close(void *p){CFBridgingRelease(p);}
