"""Conservative exact-integer subset compiled into f32 affine output columns."""
import numpy as np
LIMIT=1<<24
I64_MIN=-(1<<63)
I64_MAX=(1<<63)-1


class Unsupported(ValueError):pass


class Affine:
 def __init__(self,rule,inputs,bounds):
  self.inputs=list(inputs);self.bounds=list(bounds);n=len(inputs);self.destinations=[];self.certificates=[]
  if len(bounds)!=n or any(type(b)!=int or not 0<=b<=LIMIT for b in bounds):raise Unsupported('input bound')
  if any(rule['slots'][slot]['sort'].get('kind')!='i64' for slot in inputs):raise Unsupported('non-integer input slot')
  forms={slot:([int(i==j) for i in range(n)],0) for j,slot in enumerate(inputs)}
  def read(arg):
   if 'slot' in arg:
    if arg['slot'] not in forms:raise Unsupported('dependency is not proven input-ready scalar')
    return forms[arg['slot']]
   value=arg.get('literal')
   if type(value)!=int or arg.get('sort',{}).get('kind')!='i64':raise Unsupported('not an i64 literal')
   if abs(value)>LIMIT:raise Unsupported('inexact constant')
   return [0]*n,value
  for index,op in enumerate(rule['effects']):
   if op.get('kind')!='compute':continue
   if op.get('sort',{}).get('kind')!='i64':raise Unsupported('non-i64 operation')
   if op.get('call',{}).get('inputs')!=['i64','i64'] or op.get('call',{}).get('output')!='i64':raise Unsupported('primitive types')
   name=op.get('call',{}).get('primitive');args=op.get('args',[])
   if name not in ('+','-','*') or len(args)!=2:raise Unsupported('not supported affine primitive')
   (a,b),(c,d)=map(read,args)
   if name in ('+','-'):
    sign=1 if name=='+' else -1;coeff=[x+sign*y for x,y in zip(a,c)];offset=b+sign*d
   elif not any(a):coeff=[b*x for x in c];offset=b*d
   elif not any(c):coeff=[d*x for x in a];offset=d*b
   else:raise Unsupported('variable multiplication needs a separate fixed operator')
   bound=sum(abs(x)*v for x,v in zip(coeff,bounds))+abs(offset)
   # All possible partial sums and individual products are integral and exact.
   # Every original operation is checked, even if a later cancellation hides it.
   if bound>LIMIT or max([abs(offset)]+[abs(x) for x in coeff])>LIMIT:raise Unsupported('cannot prove exact f32 accumulation')
   dst=op['dst']
   if dst in forms:raise Unsupported('overwritten slot')
   forms[dst]=(coeff,offset);self.destinations.append(dst)
   self.certificates.append(dict(operation=index,destination=dst,absolute_accumulation_bound=bound))
  if not self.destinations:raise Unsupported('empty scalar fragment')
  self.coefficients=np.array([forms[s][0] for s in self.destinations],dtype=np.float32).T
  self.bias=np.array([forms[s][1] for s in self.destinations],dtype=np.float32)

 def eligible(self,values):
  return all(type(v)==int and I64_MIN<=v<=I64_MAX and abs(v)<=b for v,b in zip(values,self.bounds)) and len(values)==len(self.inputs)

 def embed(self,plan,positions):
  # Existing feature basis contains v/4. Multiply exact scalar coefficients by
  # four to share that basis without a second gather or feature matrix.
  weight=np.zeros((plan.weight.shape[0],len(self.destinations)),np.float32)
  for i,position in enumerate(positions):
   coeff=self.coefficients[i]*4
   if np.any(np.abs(coeff)>LIMIT):raise Unsupported('scaled coefficient not certified')
   weight[position*4]=coeff
  return np.concatenate([plan.weight,weight],axis=1),np.concatenate([plan.bias,self.bias])


def checked_reference(rule,inputs,values):
 env=dict(zip(inputs,values));out=[]
 for op in rule['effects']:
  if op.get('kind')!='compute':continue
  args=[env[x['slot']] if 'slot' in x else x['literal'] for x in op['args']]
  name=op['call']['primitive']
  if name=='+':v=args[0]+args[1]
  elif name=='-':v=args[0]-args[1]
  elif name=='*':v=args[0]*args[1]
  else:raise Unsupported('reference primitive')
  if not I64_MIN<=v<=I64_MAX:return None
  env[op['dst']]=v;out.append(v)
 return out
