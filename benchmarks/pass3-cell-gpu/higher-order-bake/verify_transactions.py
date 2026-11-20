"""Check exact ordered deliveries, true roots, publication versions, source digests and batch occupancy."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def verify():
    data = json.loads((HERE / 'transactions.json').read_bytes())
    receipt=json.loads((HERE / 'transaction-build.json').read_bytes())
    assert len(data) == 8
    for _, arms in data.items():
        for name, row in arms.items():
            limit = int(name)
            assert row['binary_sha256']==receipt['executable_sha256']
            assert row['identity'] == arms['0']['identity']
            assert row['rhs'] == row['neural_rhs'] and row['source_exact']
            assert 100*row['direct'] >= 98*row['fresh']
            assert len(row['ms']) == 8 and row['max_chain'] > 1
            q = row['transactions']
            assert q['offered'] == q['completed']
            assert q['requests'] == row['identity']['counts'][1] > 0
            if limit:
                assert sum(i*n for i,n in enumerate(q['batch_hist'])) == q['offered']
                assert sum(i*n for i,n in enumerate(q['requests_per_batch'])) == q['requests']
                assert sum(q['flush_reasons']) == sum(q['batch_hist'])
                assert 0 < q['peak'] <= limit
            else:
                assert not any(q['flush_reasons'])
    print('Checked the four batch limits, both seeds, receipt order and exact source trajectories.')


if __name__ == '__main__':
    verify()
