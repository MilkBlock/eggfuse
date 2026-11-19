"""MLX layers shared by the make and finish networks."""
import mlx.core as mx
import mlx.nn as nn

DIM = 64
K = 8
V = 4
N = 4
Q = 8
FEATURES = K + V + 2
TOKEN_WIDTH = DIM + 2 + 2*N + K + 2*V


def rope(x, coords):
    width = x.shape[-1] // 2
    freq = mx.exp(-mx.log(mx.array(10000.0)) * mx.arange(width // 2) / (width // 2))
    pieces = []
    for axis in range(2):
        part = x[..., axis * width:(axis + 1) * width]
        angle = coords[..., axis, None].astype(mx.float32) * freq
        even, odd = (part[..., 0::2], part[..., 1::2])
        pieces.append(mx.stack((mx.cos(angle) * even - mx.sin(angle) * odd, mx.sin(angle) * even + mx.cos(angle) * odd), -1).reshape(part.shape))
    return mx.concatenate(pieces, -1)


class Attention(nn.Module):

    def __init__(self):
        super().__init__()
        self.q = nn.Linear(DIM, DIM, bias=False)
        self.k = nn.Linear(DIM, DIM, bias=False)
        self.v = nn.Linear(DIM, DIM, bias=False)
        self.pq = nn.Linear(DIM, 32, bias=False)
        self.pk = nn.Linear(DIM, 32, bias=False)
        self.position_scale = mx.array(0.1)

    def prepare_memory(self, m, mpos):
        return (self.k(m), self.v(m), rope(self.pk(m), mpos))

    def from_prepared(self, q, qpos, memory, mask=None):
        k, v, pk = memory
        scores = self.q(q) @ mx.swapaxes(k, -1, -2) / DIM ** 0.5
        scores += self.position_scale * (rope(self.pq(q), qpos) @ mx.swapaxes(pk, -1, -2)) / 32 ** 0.5
        if mask is not None:
            scores = mx.where(mask, scores, -1000000000.0)
        probs = mx.softmax(scores, axis=-1)
        return (scores, probs @ v)

    def __call__(self, q, m, qpos, mpos, mask=None):
        return self.from_prepared(q, qpos, self.prepare_memory(m, mpos), mask)


def hard_symbol(logits):
    soft = mx.softmax(logits, -1)
    hard = mx.eye(logits.shape[-1])[mx.stop_gradient(mx.argmax(logits, -1))]
    return mx.stop_gradient(hard) + (soft - mx.stop_gradient(soft))


def token(latent, active, pointer, fields):
    return mx.concatenate((latent, hard_symbol(active), hard_symbol(pointer[:, :, 0]), hard_symbol(pointer[:, :, 1]), hard_symbol(fields[..., :K]), hard_symbol(fields[..., K:K + V]), hard_symbol(fields[..., K + V:])), axis=-1)


class StreamBlock(nn.Module):

    def __init__(self):
        super().__init__()
        self.norm = nn.LayerNorm(DIM)
        self.current = Attention()
        self.source = Attention()
        self.history = Attention()
        self.ff = nn.Sequential(nn.Linear(DIM, 2 * DIM), nn.GELU(), nn.Linear(2 * DIM, DIM))

    def __call__(self, q, pos, source_kv, history_kv, history_mask):
        _, z = self.current(self.norm(q), self.norm(q), pos, pos)
        q = q + z
        _, z = self.source.from_prepared(self.norm(q), pos, source_kv)
        q = q + z
        if history_kv is not None:
            _, z = self.history.from_prepared(self.norm(q), pos, history_kv, history_mask)
            q = q + z
        return q + self.ff(self.norm(q))
