// Four host-enqueued edit leaps. No device scalar is read back between leaps.
// One threadgroup draws one proposed mark, with all its dependent address decisions.
#include <metal_stdlib>
using namespace metal;
constant int W = 32;
enum Config { Cap, Slots, PCs, Tables, RowStride, OwnerStride, Vocab, Last, Seed, Leap, MarkWidth, JobCap };
enum Counters {
  Length,
  NextUid,
  Overflow,
  Jobs,
  Draws,
  Nodes,
  Pivots,
  DeletesBlocked,
  MaxBatch,
  Inserts,
  Substitutes,
  Deletes,
  LocalScans,
  PortReads
};
inline uint mix32(uint v) {
  v ^= v >> 16;
  v *= 0x7feb352du;
  v ^= v >> 15;
  v *= 0x846ca68bu;
  return v ^ (v >> 16);
}
inline float rand_unit(thread uint &s) {
  s += 0x9e3779b9u;
  return (float(mix32(s) >> 9) + 0.5f) / 8388608.0f;
}
inline int poisson(float lambda, thread uint &s) {
  // Split large means into independent Poisson draws to avoid exp underflow.
  int sum = 0;
  while (lambda > 0) {
    float part = min(lambda, 12.f);
    float cutoff = exp(-part), prod = rand_unit(s);
    while (prod > cutoff) {
      sum++;
      prod *= rand_unit(s);
    }
    lambda -= part;
  }
  return sum;
}
kernel void jobs(device const float *logits, device int *control, device int2 *job, constant int *c,
                 uint id [[thread_position_in_grid]]) {
  if (id || control[Overflow])
    return;
  int n = control[Length], count = 0;
  for (int i = 0; i <= n; i++) {
    uint s = mix32(mix32(uint(c[Seed]) ^ uint(1 + c[Leap])) + uint(2 * i));
    float3 v = float3(logits[i * 3], logits[i * 3 + 1], logits[i * 3 + 2]);
    float3 small = exp(-abs(v));
    float3 rates = (max(v, 0.f) + select(log(1.f + small), small - small * small * .5f, small < .0001f)) /
                   float(4 - c[Leap]);
    bool editor = c[Leap] < 0;
    int add = editor ? int(rint(rates.x * (4 - c[Leap]))) : poisson(rates.x, s);
    float total = rates.y + rates.z;
    if (i < n && (editor ? max(v.y, v.z) > 0.f : rand_unit(s) < (1.f - exp(-total)))) {
      int op = editor ? (v.z > v.y ? 2 : 1) : (rand_unit(s) * total > rates.y ? 2 : 1);
      if (count < c[JobCap])
        job[count] = int2(i, op);
      count++;
    }
    for (int k = 0; k < add; k++) {
      if (count < c[JobCap])
        job[count] = int2(i, 0);
      count++;
    }
  }
  control[Jobs] = count;
  control[MaxBatch] = max(control[MaxBatch], count);
  if (count > c[JobCap])
    control[Overflow] = 1;
}
// FP32 matvec with one SIMD group; each lane owns a row and all weights are resident.
inline bool choose(device const float *w, int h, threadgroup float *x, threadgroup float *a,
                   threadgroup float *b, int lane, thread uint &s) {
  for (int i = lane; i < h; i += 32) {
    float u = w[99 * h + i];
    for (int j = 0; j < 99; j++)
      u = fma(w[i * 99 + j], x[j], u);
    a[i] = tanh(u);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  int off = 100 * h;
  for (int i = lane; i < h; i += 32) {
    float u = w[off + h * h + i];
    for (int j = 0; j < h; j++)
      u = fma(w[off + i * h + j], a[j], u);
    b[i] = tanh(u);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  off += h * h + h;
  float u = 0;
  for (int j = lane; j < h; j += 32)
    u = fma(w[off + j], b[j], u);
  float score = simd_sum(u) + w[off + h];
  return rand_unit(s) < 1.f / (1.f + exp(-score));
}
inline float rot(device const float *v, int k, int j) {
  float phi = float(k) * exp(float(j / 2) * (-log(10000.f) / 16.f));
  return j % 2 ? v[j - 1] * sin(phi) + v[j] * cos(phi) : v[j] * cos(phi) - v[j + 1] * sin(phi);
}
// Physical representation of a reference: (positive global row, op, requested version)
// or (negative local uid - 1, named output op, 0). Global row zero is padding.
kernel void draw(device const int2 *job, device int *control, constant int *c, device const int *draft,
                 device const float *embeds, device int *out, device const int *vocab,
                 device const float *graphs, device const int *roles, device const float *slots,
                 device const int *outputs, device const float *localcodes, device const int *tabrows,
                 device const int *sizes, device const int *rowmeta, device const float *keys,
                 device const int *ownerpc, device const int *projection, device const float *weights,
                 device const float *gru, device const float *ctx, device int *perjob,
                 device const int *membership, device const int *order,
                 uint g [[threadgroup_position_in_grid]], uint l [[thread_index_in_threadgroup]]) {
  if (control[Overflow] || int(g) >= control[Jobs])
    return;
  int stride = 2 + 3 * c[Slots], pos = job[g].x, op = job[g].y;
  device int *result = out + g * stride;
  if (l == 0)
    result[1] = -1;
  if (op == 1)
    return;
  int lane = int(l), rid = -1, tid = -1, pivots = 0, visits = 0, localVisits = 0, portReads = 0;
  threadgroup float x[99], a[MARK_H], b[MARK_H], q[32], tmp[32], gates[192];
  uint random = mix32(mix32(uint(c[Seed]) ^ uint(33 + c[Leap])) + 2 * g + 1);
  q[lane] = op == 2 ? tanh(ctx[lane] + embeds[pos * 32 + lane]) : ctx[lane];
  threadgroup_barrier(mem_flags::mem_threadgroup);
  int lo = 0, hi = c[Vocab];
  while (hi - lo > 1) {
    int mid = (lo + hi) / 2;
    x[lane] = q[lane];
    x[32 + lane] = graphs[32 * vocab[(lo + mid - 1) / 2] + lane];
    x[64 + lane] = graphs[32 * vocab[(mid + hi - 1) / 2] + lane];
    if (lane < 3)
      x[96 + lane] = float(lane == 0);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    bool right = choose(weights, MARK_H, x, a, b, lane, random);
    if (right)
      lo = mid;
    else
      hi = mid;
    visits++;
    pivots += 2;
  }
#ifdef SET_PAGE
  if (lane == 0) {
    atomic_fetch_add_explicit((device atomic_int *)(control+14), visits, memory_order_relaxed);
    atomic_fetch_add_explicit((device atomic_int *)(control+15), pivots+1, memory_order_relaxed);
  }
#endif
  tid = vocab[lo];
  rid = tid / 2;
  q[lane] = tanh(q[lane] + graphs[32 * tid + lane]);
  int anchor = 0, producer = -1, owner = 0;
  bool useProjection = false, success = true;
  for (int i = 0; i < c[Slots]; i++) {
    int tab = roles[rid * c[Slots] + i];
    if (tab < 0)
      break;
    device const float *slot = slots + 32 * (rid * c[Slots] + i);
    tmp[lane] = tanh(q[lane] + slot[lane]);
    // Fixed owner output projection requires a previously selected physical owner.
    if (i == 1 && anchor > 0) {
      owner = rowmeta[5 * anchor + 2];
      producer = rowmeta[5 * anchor + 3];
      bool any = false;
      if (producer >= 0)
        for (int j = 1; j < c[Slots]; j++) {
          int tabj = roles[rid * c[Slots] + j];
          if (tabj < 0)
            break;
          if (projection[producer * c[Tables] + tabj] >= 0)
            any = true;
        }
      if (any) {
        x[lane] = tmp[lane];
        x[32 + lane] = keys[32 * anchor + lane];
        x[64 + lane] = slot[lane];
        if (lane < 3)
          x[96 + lane] = float(lane == 2);
        threadgroup_barrier(mem_flags::mem_threadgroup);
        useProjection = choose(weights, MARK_H, x, a, b, lane, random);
        visits++;
      }
    }
    int pc = useProjection ? projection[producer * c[Tables] + tab] : -1;
    int picked = 0, localId = -1, localPc = -1, localTid = -1;
    if (pc >= 0) {
      picked = ownerpc[owner * c[OwnerStride] + pc];
      portReads++;
    } else {
      int nlocal = 0, first = -1;
      for (int j = 0; j < pos; j++) {
        int t = draft[j * stride + 1];
        for (int ord = 0; ord < c[PCs]; ord++) {
          int k = order[(t / 2) * c[PCs] + ord];
          if (outputs[(t / 2) * c[PCs] + k] == tab) {
            if (first < 0)
              first = t * c[PCs] + k;
            nlocal++;
          }
          localVisits++;
        }
      }
      bool local = false;
      if (nlocal) {
        x[lane] = tmp[lane];
        x[32 + lane] = 0;
        x[64 + lane] = localcodes[first * 32 + lane];
        if (lane < 3)
          x[96 + lane] = float(lane == 2);
        threadgroup_barrier(mem_flags::mem_threadgroup);
        local = choose(weights, MARK_H, x, a, b, lane, random);
        visits++;
      }
      if (!local) {
        int hint = op == 2 && roles[(draft[pos * stride + 1] / 2) * c[Slots] + i] >= 0
                       ? draft[pos * stride + 2 + i * 3]
                       : 0;
        int copy = (hint > 0 && (membership[hint * ((c[Tables] + 31) / 32) + tab / 32] & (1u << (tab % 32))))
                       ? hint
                       : c[Last];
        if (copy > 0 && (membership[copy * ((c[Tables] + 31) / 32) + tab / 32] & (1u << (tab % 32)))) {
          x[lane] = tmp[lane];
          x[32 + lane] = keys[32 * copy + lane];
          x[64 + lane] = 0;
          if (lane < 3)
            x[96 + lane] = float(lane == 2);
          threadgroup_barrier(mem_flags::mem_threadgroup);
          if (!choose(weights, MARK_H, x, a, b, lane, random))
            picked = copy;
          visits++;
          pivots++;
        }
      }
      if (!picked) {
        lo = 0;
        hi = local ? nlocal : sizes[tab];
        if (hi == 0) {
          success = false;
          break;
        }
        while (hi - lo > 1) {
          int mid = (lo + hi) / 2, li = (lo + mid - 1) / 2, ri = (mid + hi - 1) / 2;
          int aa = 0, bb = 0;
          if (local) {
            int n = 0;
            for (int j = 0; j < pos; j++) {
              int t = draft[j * stride + 1];
              for (int ord = 0; ord < c[PCs]; ord++)
                if (outputs[(t / 2) * c[PCs] + order[(t / 2) * c[PCs] + ord]] == tab) {
                  int k = order[(t / 2) * c[PCs] + ord];
                  if (n == li)
                    aa = t * c[PCs] + k;
                  if (n == ri)
                    bb = t * c[PCs] + k;
                  n++;
                }
            }
          } else {
            aa = tabrows[tab * c[RowStride] + li];
            bb = tabrows[tab * c[RowStride] + ri];
          }
          x[lane] = tmp[lane];
          x[32 + lane] = local ? localcodes[32 * aa + lane] : keys[32 * aa + lane];
          x[64 + lane] = local ? localcodes[32 * bb + lane] : keys[32 * bb + lane];
          if (lane < 3)
            x[96 + lane] = float(lane == 1);
          threadgroup_barrier(mem_flags::mem_threadgroup);
          if (choose(weights, MARK_H, x, a, b, lane, random))
            lo = mid;
          else
            hi = mid;
          visits++;
          pivots += 2;
        }
        if (local) {
          int n = 0;
          for (int j = 0; j < pos; j++) {
            int t = draft[j * stride + 1];
            for (int ord = 0; ord < c[PCs]; ord++)
              if (outputs[(t / 2) * c[PCs] + order[(t / 2) * c[PCs] + ord]] == tab) {
                int k = order[(t / 2) * c[PCs] + ord];
                if (n == lo) {
                  localId = draft[j * stride];
                  localPc = k;
                  localTid = t;
                }
                n++;
              }
          }
        } else
          picked = tabrows[tab * c[RowStride] + lo];
      }
    }
    if (localId < 0 && (picked <= 0 || rowmeta[5 * picked] != tab)) {
      success = false;
      break;
    }
    if (i == 0)
      anchor = picked;
    if (lane == 0) {
      result[2 + 3 * i] = localId < 0 ? picked : -1 - localId;
      result[3 + 3 * i] = localId < 0 ? 0 : localPc;
      result[4 + 3 * i] = localId < 0 ? rowmeta[5 * picked + 1] : 0;
    }
    tmp[lane] =
        (localId < 0 ? keys[32 * picked + lane] : localcodes[(localTid * c[PCs] + localPc) * 32 + lane]) +
        slot[lane];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for (int k = lane; k < 96; k += 32) {
      float u = gru[6144 + k], v = gru[6240 + k];
      for (int j = 0; j < 32; j++) {
        u = fma(tmp[j], gru[k * 32 + j], u);
        v = fma(q[j], gru[3072 + k * 32 + j], v);
      }
      gates[k] = u;
      gates[96 + k] = v;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    float reset = 1 / (1 + exp(-gates[lane] - gates[96 + lane])),
          z = 1 / (1 + exp(-gates[32 + lane] - gates[128 + lane]));
    q[lane] = (1 - z) * tanh(gates[64 + lane] + reset * gates[160 + lane]) + z * q[lane];
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
  if (lane == 0) {
    result[1] = success ? tid : -1;
    perjob[g * 4] = visits;
    perjob[g * 4 + 1] = pivots;
    perjob[g * 4 + 2] = localVisits;
    perjob[g * 4 + 3] = portReads;
  }
}

kernel void edit_vectors(device const int *generated, device const int *control, constant int *c,
                         device const int2 *job, device const int *roles, device const float *slots,
                         device const float *graphs, device const float *idvec, device const float *keys,
                         device float *encoded, uint gid [[thread_position_in_grid]]) {
  int g = gid / 32, j = gid % 32;
  if (control[Overflow] || g >= control[Jobs] || job[g].y == 1)
    return;
  int stride = 2 + 3 * c[Slots];
  device const int *item = generated + g * stride;
  int t = item[1];
  if (t < 0)
    return;
  float ext = 0, loc = 0;
  int n = 0;
  for (int i = 0; i < c[Slots] && roles[(t / 2) * c[Slots] + i] >= 0; i++) {
    int ref = item[2 + 3 * i];
    if (ref > 0) {
      ext += rot(idvec + 32 * ref, n, j) + rot(keys + 32 * ref, n, j);
      n++;
    } else
      loc += rot(slots + 32 * ((t / 2) * c[Slots] + i), item[3 + 3 * i], j);
  }
  encoded[gid] = tanh(graphs[t * 32 + j] + ext / sqrt(float(max(1, n))) + loc);
}
kernel void apply_jobs(device int *draft, device float *embeds, device int *control, constant int *c,
                       device const int2 *job, device const int *generated, device const float *encoded,
                       device const int *roles, device const int *outputs, device const int *perjob,
                       uint id [[thread_position_in_grid]]) {
  if (id || control[Overflow])
    return;
  int stride = 2 + 3 * c[Slots], n = control[Length], end = control[Jobs];
  while (end > 0) {
    int pos = job[end - 1].x, begin = end - 1;
    while (begin > 0 && job[begin - 1].x == pos)
      begin--;
    for (int g = begin; g < end; g++) {
      int op = job[g].y;
      device const int *item = generated + g * stride;
      if (op != 1) {
        control[Draws]++;
        control[Nodes] += perjob[g * 4];
        control[Pivots] += perjob[g * 4 + 1];
        control[LocalScans] += perjob[g * 4 + 2];
        control[PortReads] += perjob[g * 4 + 3];
        if (item[1] < 0)
          continue;
      }
      if (op) {
        bool legal = true;
        int uid = draft[pos * stride];
        for (int j = pos + 1; j < n && legal; j++) {
          device const int *later = draft + j * stride;
          for (int k = 0; k < c[Slots] && roles[(later[1] / 2) * c[Slots] + k] >= 0; k++) {
            if (later[2 + 3 * k] == -1 - uid &&
                (op == 1 || outputs[(item[1] / 2) * c[PCs] + later[3 + 3 * k]] !=
                                roles[(later[1] / 2) * c[Slots] + k])) {
              legal = false;
              break;
            }
          }
        }
        if (!legal) {
          control[DeletesBlocked]++;
          continue;
        }
        if (op == 1) {
          for (int j = pos; j < n - 1; j++) {
            for (int k = 0; k < stride; k++)
              draft[j * stride + k] = draft[(j + 1) * stride + k];
            for (int k = 0; k < 32; k++)
              embeds[j * 32 + k] = embeds[(j + 1) * 32 + k];
          }
          n--;
          control[Deletes]++;
          continue;
        }
        control[Substitutes]++;
      } else {
        if (n >= c[Cap]) {
          control[Overflow] = 1;
          return;
        }
        for (int j = n; j > pos; j--) {
          for (int k = 0; k < stride; k++)
            draft[j * stride + k] = draft[(j - 1) * stride + k];
          for (int k = 0; k < 32; k++)
            embeds[j * 32 + k] = embeds[(j - 1) * 32 + k];
        }
        n++;
        draft[pos * stride] = control[NextUid]++;
        control[Inserts]++;
      }
      for (int k = 1; k < stride; k++)
        draft[pos * stride + k] = item[k];
      for (int k = 0; k < 32; k++)
        embeds[32 * pos + k] = encoded[32 * g + k];
    }
    end = begin;
  }
  control[Length] = n;
}
kernel void rate_features(device const float *draft, device const float *se, device const int *control,
                          constant int *c, device float *feat, uint idx [[thread_position_in_grid]]) {
  int i = idx / 166, k = idx % 166, n = control[Length];
  float v = 0;
  if (k < 64)
    v = se[k];
  else if (k < 160) {
    int j = (k - 64) % 32;
    float cur = i < n ? draft[i * 32 + j] : 0;
    v = k < 96 ? cur
               : (k < 128 ? abs(cur - (i > 0 ? draft[(i - 1) * 32 + j] : 0))
                          : abs(cur - (i + 1 < n ? draft[(i + 1) * 32 + j] : 0)));
  } else
    switch (k) {
    case 160:
      v = max(c[Leap], 0) * .25f;
      break;
    case 161:
      v = float(i < n);
      break;
    case 162:
      v = float(i > 0);
      break;
    case 163:
      v = float(i + 1 < n);
      break;
    case 164:
      v = log(1.f + float(n));
      break;
    case 165:
      v = float(i) / float(max(n, 1));
      break;
    }
  feat[idx] = v;
}

// Continuation across pages. Only the chosen request and counters cross the issue/Seal boundary.
kernel void page_begin(device int *ctl, device const int *draft, constant int *c,
                       uint id [[thread_position_in_grid]]) {
  if (id || ctl[Overflow])
    return;
  int uid = 0;
  for (int i = 0; i < ctl[Length]; i++)
    uid = max(uid, 1 + draft[i * (2 + 3 * c[Slots])]);
  ctl[NextUid] = uid;
}
kernel void page_end(device int *ctl, device int *draft, device float *emb, device int *request,
                     device const int *roles, device const int *scheduled, constant int *c,
                     uint id [[thread_position_in_grid]]) {
  if (id || ctl[Overflow])
    return;
  ctl[15]++;
  int n = ctl[Length], stride = 2 + 3 * c[Slots];
  if (!n)
    return;
  int r = draft[1] / 2;
  bool ready = bool(scheduled[r]);
  for (int i = 0; i < c[Slots] && roles[r * c[Slots] + i] >= 0; i++)
    if (draft[2 + 3 * i] <= 0 || draft[4 + 3 * i] < 0)
      ready = false;
  if (ready) {
    for (int k = 0; k < stride; k++)
      request[k] = draft[k];
    for (int j = 0; j < n - 1; j++) {
      for (int k = 0; k < stride; k++)
        draft[j * stride + k] = draft[(j + 1) * stride + k];
      for (int k = 0; k < 32; k++)
        emb[j * 32 + k] = emb[(j + 1) * 32 + k];
    }
    ctl[Length]--;
    ctl[14] = 1;
    ctl[Overflow] = 2; // Stop subsequent proposals until a real reply.
  }
  ctl[16] += ctl[Length];
}
kernel void fix_refs(device int *draft, device const int *roles, device const int *meta,
                     device const int *identity, device const int *pcmap, constant int *c,
                     uint idx [[thread_position_in_grid]]) {
  int stride = 2 + 3 * c[Slots], j = idx / c[Slots], i = idx % c[Slots];
  device int *item = draft + j * stride;
  if (roles[(item[1] / 2) * c[Slots] + i] < 0)
    return;
  device int *ref = item + 2 + 3 * i;
  if (c[Seed] >= 0 && ref[0] == -1 - c[Seed]) {
    ref[0] = pcmap[ref[1]];
    ref[1] = 0;
    ref[2] = -1;
  } else if (c[Seed] < 0 && ref[0] > 0 && ref[2] < 0 && identity[3 * ref[0] + 2] != 0 &&
             meta[5 * ref[0]] >= 0)
    ref[2] = meta[5 * ref[0] + 1];
}
inline float bitfield(int value, int bit) { return float((uint(value) >> min(31, bit)) & 1u) * 2 - 1; }
kernel void refresh_vec(device const int *draft, device const int *roles, device const int *meta,
                        device const int *identity, device const float *graphs, device const float *keys,
                        device const float *weight, device const float *slots, device float *emb,
                        constant int *c, uint gid [[thread_position_in_grid]]) {
  int j = gid % 32, tok = gid / 32, stride = 2 + 3 * c[Slots];
  device const int *item = draft + tok * stride;
  int t = item[1], n = 0;
  float ext = 0, local = 0, frequency = exp(float(j / 2) * (-log(10000.f) / 16.f));
  for (int i = 0; i < c[Slots] && roles[(t / 2) * c[Slots] + i] >= 0; i++) {
    int a = item[2 + 3 * i], pc = item[3 + 3 * i], version = item[4 + 3 * i];
    if (a < 0) {
      local += rot(slots + 32 * ((t / 2) * c[Slots] + i), pc, j);
      continue;
    }
    int owner = identity[3 * a], op = identity[3 * a + 1], even = j & ~1;
    float first = keys[32 * a + even], second = keys[32 * a + even + 1];
    for (int k = 0; k < 32; k++) {
      float v = bitfield(owner, k) + bitfield(op, k + 7) * .5f + bitfield(version, k + 14) / 3.f;
      first = fma(weight[even * 32 + k], v, first);
      second = fma(weight[(even + 1) * 32 + k], v, second);
    }
    float phi = n * frequency;
    ext += j % 2 ? first * sin(phi) + second * cos(phi) : first * cos(phi) - second * sin(phi);
    n++;
  }
  emb[gid] = tanh(graphs[t * 32 + j] + local + ext / sqrt(float(max(n, 1))));
}
