"""Train a causal shared work predictor; solve the finite-budget offline pricing oracle."""
import numpy as np
import networkx as nx
from capture import policy


class Trace:
    def __init__(self,folder,window=32):
        with np.load(folder/'regions.npz') as f:self.samples=f['windows'].astype(np.int64)
        with np.load(folder/'output.npz') as z:
            u=z['unions'][:,0].astype(np.int64)
            self.unions=np.bincount((u-1)//window,minlength=len(self.samples))
        self.live=self.samples[:,:,0]
        self.gain=self.samples[:,:,6]-self.unions[:,None]
        self.x=self.samples[:,:,:6]
    def select(self,p):
        score=(self.x.astype(np.float32)@np.array(p['weights'],dtype=np.float32))+np.float32(p['bias'])
        prev=set();out=[]
        for t,s in enumerate(score):
            priority=s.copy()
            new=[i for i in range(len(s)) if i not in prev]
            priority[new]-=self.live[t,new]*p['build_price']
            ranked=np.argsort(-priority,kind='stable')
            ranked=[int(i) for i in ranked if self.live[t,i]>0 and priority[i]>0]
            out.append(set(ranked[:p['budget']]))
            prev=out[-1]
        return out
    def work(self,chosen):
        saved=notify=born=exits=0;before=set()
        for t,now in enumerate(chosen):
            assert all(self.live[t,i]>0 for i in now)
            saved+=sum(int(self.samples[t,i,6]) for i in now)
            notify+=len(now)*int(self.unions[t])
            born+=sum(int(self.live[t,i]) for i in now-before)
            exits+=len(before-now)
            before=now
        return dict(clean_rows_saved=saved,slot_probes=notify,admitted_live_rows=born,exits=exits,
                    priced_work=saved-notify-born-exits)
    def oracle(self,budget):
        # One unit of flow = one reusable directory slot. Crossing to another
        # region incurs release and construction. Carrying the slot is free.
        graph=nx.DiGraph()
        T=len(self.samples)
        for t in range(T):
            graph.add_edge(t,t+1,capacity=budget,weight=0)
            for i in np.flatnonzero(self.live[t]>0):
                i=int(i);pin=(t,i,0);pout=(t,i,1)
                graph.add_edge(t,pin,capacity=1,weight=int(self.live[t,i]))
                graph.add_edge(pin,pout,capacity=1,weight=-int(self.gain[t,i]))
                graph.add_edge(pout,t+1,capacity=1,weight=int(t<T-1))
                if t and self.live[t-1,i]>0:graph.add_edge((t-1,i,1),pin,capacity=1,weight=0)
        graph.nodes[0]['demand']=-budget;graph.nodes[T]['demand']=budget
        cost,flow=nx.network_simplex(graph)
        chosen=[{int(i) for i in np.flatnonzero(self.live[t]>0) if flow[(t,int(i),0)][(t,int(i),1)]} for t in range(T)]
        assert self.work(chosen)['priced_work']==-cost
        return chosen


def fit(traces,budget):
    p=policy(budget);p.update(capture=False)
    # Static density / write-activity threshold: calibrate exclusively on
    # training families. Include idle and maintenance costs in model selection.
    candidates=[]
    for penalty in (0,1,4,16):
        for floor in (0,8,24):
            test=dict(p,weights=[2,0,0,-penalty,0,0],bias=-floor,build_price=1)
            score=np.mean([s.work(s.select(test))['priced_work']/max(1,s.samples[:,:,6].sum()) for s in traces])
            candidates.append((score,test))
    static=max(candidates,key=lambda pair:pair[0])[1]
    X=[];Y=[];W=[]
    for t in traces:
        eligible=t.live>0
        x=t.x[eligible].astype(float)
        X.append(x);Y.append(t.gain[eligible].astype(float));W.extend([1/len(x)]*len(x))
    X=np.concatenate(X);Y=np.concatenate(Y);W=np.array(W)/len(traces)
    mean=np.average(X,axis=0,weights=W)
    sd=np.sqrt(np.average((X-mean)**2,axis=0,weights=W)).clip(.001)
    z=(X-mean)/sd
    ymean=float(np.average(Y,weights=W))
    w=np.linalg.solve((z.T*W)@z+.01*np.eye(X.shape[1]),(z.T*W)@(Y-ymean))/sd
    learned=dict(p,weights=w.tolist(),bias=float(ymean-mean@w),build_price=1)
    return static,learned
