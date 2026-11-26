// Joint endpoint proposal, followed by a uniform-reveal leap on editable slots.
// Generation jobs retain their order solely for stable local references.
kernel void set_jobs(device const float *logits, device int *ctl, device int2 *jobs,
                     constant int *cfg, constant int2 &method_steps,
                     uint gid [[thread_position_in_grid]]) {
  if (gid) return;
  int n=ctl[Length], cap=cfg[Cap], count=0, method=method_steps.x, steps=method_steps.y;
  for (int i=0;i<cap;i++) {
    uint seed=mix32(uint(cfg[Seed]) ^ mix32(uint(i+1)) ^ mix32(uint(cfg[Leap]+1)));
    if (method==2 && rand_unit(seed) >= 1.f/float(steps-cfg[Leap])) continue;
    int action=2;
    if (method) {
      float3 v=float3(logits[3*i],i<n?logits[3*i+1]:-1.e4f,logits[3*i+2]);
      v=exp(v-max(v.x,max(v.y,v.z)));
      float k=rand_unit(seed)*(v.x+v.y+v.z);
      action=k<v.x ? 0 : k<v.x+v.y ? 1 : 2;
    }
    if (action==0 || (action==1 && i>=n)) continue;
    jobs[count++]=int2(min(i,n),action==1?1:i<n?2:0);
  }
  ctl[Jobs]=count;
  ctl[MaxBatch]=max(ctl[MaxBatch],count);
}
