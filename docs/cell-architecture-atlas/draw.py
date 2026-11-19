"""Generate editable SVG small multiples for the Cell architecture atlas (stdlib only)."""
from pathlib import Path
from html import escape

OUT = Path(__file__).parent / "figures"
INK="#162f42"; SUB="#496478"; LINE="#8396a1"; BG="#f5f7f7"
PALETTE={"n":("#e0ebf5","#305e81"),"s":("#d9efea","#247568"),
         "t":("#eee7f6","#775692"),"v":("#f8ebd2","#946422"),
         "x":("#f0f1f2","#7a858b"),"w":("#fff","#415765")}

class Art:
    def __init__(self): self.e=[]
    def put(self,x): self.e.append(x)
    def rect(self,x,y,w,h,fill="white",stroke="none",r=5,dash=False):
        self.put(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"'+(' stroke-dasharray="5 4"' if dash else '')+'/>')
    def txt(self,x,y,s,size=15,c=INK,anchor="middle",bold=False):
        self.put(f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{c}" text-anchor="{anchor}">{escape(str(s))}</text>')
    def path(self,points,c=LINE,dash=False,arrow=True):
        self.put(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{c}" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"'+(' stroke-dasharray="5 4"' if dash else '')+(' marker-end="url(#arrow)"' if arrow else '')+'/>')
    def link(self,x,y,z,t,**kw):self.path([(x,y),(z,t)],**kw)
    def node(self,x,y,w,label,kind="n",h=31):
        fill,col=PALETTE[kind];self.rect(x-w/2,y-h/2,w,h,fill,col,5,kind=="t");self.txt(x,y+5,label,15,col,bold=True)
    def grid(self,x,y,rows,cols,*,cell=20,fill=None,dx=5,dy=6):
        for i in range(rows):
            for j in range(cols):
                on=True if fill is None else fill(i,j)
                a,b=PALETTE["n" if on else "x"];self.rect(x+j*(cell+dx),y+i*(cell+dy),cell,cell,a if on else "white",b,3,not on)
    def port(self,x,y,label,kind="s"):
        a,b=PALETTE[kind];self.put(f'<circle cx="{x}" cy="{y}" r="16" fill="{a}" stroke="{b}" stroke-width="1.7"/>');self.txt(x,y+5,label,14,b,bold=True)

def chain(a,labels,kinds=None):
    kinds=kinds or ["n"]*len(labels)
    ys=[58+(103/(len(labels)-1))*i for i in range(len(labels))]
    for y,z in zip(ys,ys[1:]):a.link(155,y+16,155,z-19,dash=kinds[ys.index(z)]=="t")
    for y,lab,k in zip(ys,labels,kinds):a.node(155,y,194,lab,k)

def graph(a,mode):
    if mode==0:chain(a,["template ID","embedding lookup","shared pointer H"],["s","n","n"]);return
    nodes=[(65,59,"i"),(65,111,"t"),(156,59,"i"),(156,111,"x")]
    a.txt(66,33,"Request",14);a.txt(156,33,"Pair",14)
    if mode in (2,3):
        a.link(84,59,137,59,c=PALETTE["s"][1]);a.path([(156,128),(156,148),(208,148)],c=PALETTE["s"][1]);a.path([(65,128),(65,168),(208,168)],c=PALETTE["s"][1])
        a.txt(111,51,"eq",11);a.txt(163,139,"copy",11,anchor="start")
        a.node(247,157,75,"GNN")
        targets=[170] if mode==2 else [80,170,260]
        for index,cx in enumerate(targets):
            a.path([(247,173),(247,182),(cx,182),(cx,192)])
            a.node(cx,204,61,"z(G)" if mode==2 else ["z(i)","z(t)","z(x)"][index],"s",h=20)
    else:
        a.node(231,159,112,"role encoder");a.path([(84,111),(113,143),(168,159)]);a.link(171,117,189,141);a.txt(143,192,"type · position · role",15)
    for x,y,l in nodes:a.port(x,y,l)

def heads(a,shared):
    for x,rule in [(82,"make"),(225,"finish")]:a.node(x,54,108,rule,"s")
    if shared:
        a.link(82,71,138,100);a.link(225,71,176,100);a.node(155,118,164,"shared pointer H")
        a.link(155,135,81,166);a.link(155,135,228,166)
    else:
        for x,lab in [(82,"pointer M"),(225,"pointer F")]:
            a.link(x,71,x,99);a.node(x,118,112,lab);a.link(x,135,x,165)
    for x in [82,225]:a.node(x,184,111,"binding","w")

def address(a,axes):
    x,y=55,47;a.grid(x,y,3,5,cell=23,dx=9,dy=13)
    a.path([(65,57),(33,57),(33,129),(147,129)],c="#946422")
    a.rect(151,119,23,23,"#f3cd80","#946422",3)
    a.txt(242,68,"source",14);a.txt(243,132,"target",14)
    a.node(154,178,258,["rL + t","RoPE(row) | RoPE(pos)","row / pos / port","(rL + t)P + p"][axes],"s")
    if axes==2:
        for j in range(3):a.rect(153+j*6,122,4,16,"#946422" if j==1 else "white","#946422",1)

def width(a,r):
    n=8//r;c=22;dx=5;dy=8;w=n*(c+dx)-dx;h=r*(c+dy)-dy
    x=(310-w)/2;y=100-h/2
    a.grid(x,y,r,n,cell=c,dx=dx,dy=dy)
    a.link(x,y+h+13,x+w,y+h+13);a.txt(155,190,f"{r} row{'s' if r>1 else ''}  /  {n} steps",16)
    a.txt(155,35,"same policy at each slot",14)

def curriculum(a,i):
    chain(a,["1-row supervised",["copy frozen policy","multi-row targets","joint reward R","advantage per row"][i],"2 rows emit together"],["n","w" if i==0 else "t","n"])
    a.txt(155,198,["0 updates","matched budget","same reward to both","others held fixed"][i],14,SUB)

def gate(a,adaptive):
    a.node(155,41,168,"row gate" if adaptive else "fixed width", "n" if adaptive else "s")
    a.link(155,58,155,80)
    a.grid(89,89,2,4,cell=27,fill=(lambda i,j:i==0 and j<2) if adaptive else None)
    a.txt(155,208,"1 → 1 → 0 → 0 active" if adaptive else "2 → 2 → 2 → 2 active",15)

def ready(a,mode):
    if mode=="predict":
        a.node(155,37,200,"current wave + history","s")
        a.link(155,53,155,71);a.node(155,88,200,"propose C, V")
        a.link(155,105,155,122);a.node(155,140,202,"exact guard (optional)","v")
        a.link(155,157,155,174);a.node(155,191,207,"publish at finish","s")
        return
    for x,name in [(58,"P0"),(148,"P1"),(250,"U")]:
        a.node(x,36,52,name,"s")
    if mode=="local":
        a.link(58,53,79,78);a.link(148,53,115,78);a.link(250,53,250,78)
        a.node(96,96,140,"same-key join","v");a.node(250,96,82,"project","v")
        for x,name in [(96,"private C"),(250,"private V")]:
            a.link(x,113,x,128);a.node(x,145,94,name)
        a.link(96,161,115,178);a.link(250,161,203,178)
        a.node(155,194,185,"publish at finish","s")
    else:
        for x in (58,148,250):a.link(x,53,x,79)
        a.node(155,97,252,"wait for finish","x")
        for x in (96,222):a.link(x,114,x,130)
        a.node(96,147,88,"join C");a.node(222,147,94,"project V")
        a.link(96,164,115,179);a.link(222,164,199,179)
        a.node(155,195,185,"publish at finish","s")


def projection(a,i):
    a.node(72,53,88,"latent");a.node(230,53,110,"pointers")
    a.node(155,121,158,"field head" if i==0 else "plan.gather","n" if i==0 else "s")
    if i==0:a.link(72,70,117,103)
    else:a.link(230,71,191,103)
    a.node(155,181,128,"Pair token","w");a.link(155,138,155,163)
    a.path([(230,70),(271,83),(271,181),(222,181)])
    if i==2:
        a.path([(72,71),(38,96),(38,134)],dash=True,c="#775692");a.node(44,151,78,"aux loss","t")

def tokenmask(a,i):
    for x,w,label,b in [(14,121,"latent",i!=2),(135,66,"refs",i==0),(201,94,"fields",True)]:
        a.rect(x,75,w,44,*PALETTE["n" if b else "x"],r=2,dash=not b)
        a.txt(x+w/2,101,label if b else "×",18)
    a.txt(155,54,"Pair from make",15)
    a.link(155,122,155,151);a.node(155,172,156,"finish + Request")
    a.txt(155,209,"64D latent · explicit identity",14,SUB)

def recurrence(a,typed):
    a.node(72,54,92,"emit");a.node(235,54,103,"consume")
    a.path([(72,72),(72,119),(103,119)])
    a.node(161,119,108,"symbols" if typed else "latent","s" if typed else "n")
    a.path([(218,119),(236,119),(236,74)])
    a.path([(250,74),(271,95),(271,170),(50,170),(50,74)],dash=False)
    a.txt(155,200,"repeat Compose × 12",15)

def allocate(a,free):
    for j,lab in enumerate(["A0","A1","A2"]):a.node(65+j*89,54,62,lab,"s")
    for j in range(3):
        if free:
            for k in range(3):a.link(65+j*89,71,65+k*89,140,c="#9bb0b7")
        else:a.link(65+j*89,71,65+j*89,140)
    for j,lab in enumerate(["q0","q1","ø" if free else "q2"]):a.node(65+j*89,160,62,lab,"x" if lab=="ø" else "n")
    if free:
        a.link(87,178,124 if free==2 else 223,178,dash=False)
    a.txt(155,205,["illustrated: 3 slots","query mix: all rows","query mix: row-local"][free],14,SUB)

def coverage(a,on):
    for x in (70,155,240):a.node(x,55,61,"slot")
    for x in (70,155,240):a.link(x,71,155,101,dash=True,c="#775692")
    a.node(155,119,205,"Hungarian alignment","t")
    if on:
        a.link(155,137,155,157,dash=True,c="#775692");a.node(155,178,224,"+ count + coverage","t")
    else:a.txt(155,183,"per-slot supervised loss",16)

def history(a,i):
    for x,l in [(80,'row 0'),(222,'row 1')]:
        a.node(x,52,93,l)
        a.node(x,155,93,"next")
        a.link(x,69,x,135,dash=i==0,c=LINE if i==0 else "#305e81")
    if i<2:
        a.link(88,71,211,136,dash=i==0);a.link(211,71,90,136,dash=i==0)
    a.txt(155,106, "zero payload" if i==0 else " ",14,SUB)
    a.txt(155,199,["matched blind path","generated history","same-row history only"][i],14)

def locality(a,i):
    if i==2:
        a.node(155,48,218,"conditional local port pairs","s")
        a.link(155,65,155,84);a.node(155,102,203,"one external union","v")
        a.link(155,119,155,139);a.node(155,157,210,"verify path to source","s")
        a.txt(155,201,"emit with original parent",15,SUB)
        return
    for x,name in ((78,"owner 0"),(230,"owner 1")):
        a.node(x,45,104,name,"s")
    if i==0:
        a.link(78,62,124,97);a.link(230,62,187,97)
        a.node(155,114,175,"global bank: 2 × 16")
        a.link(155,131,155,151);a.node(155,170,184,"request activation","n")
    else:
        for x in (78,230):
            a.link(x,62,x,85);a.node(x,104,105,"16 floats")
        a.path([(230,121),(230,140),(161,140),(161,159)],c="#946422")
        a.path([(78,121),(78,140),(122,140),(122,159)])
        a.node(144,177,207,"versioned parent reply","v")
    a.txt(155,209,"shared producer and requests",14,SUB)

def union(a,i):
    a.port(66,57,"p");a.port(245,57,"q")
    a.link(84,57,226,57,c="#946422");a.txt(155,48,"p = q",15);a.link(155,60,155,88,c="#946422")
    if i==0:chain_low(a,"merge + repair","read new epoch")
    else:chain_low(a,"pending equality","flush before observer")
def chain_low(a,l1,l2):
    a.node(155,108,195,l1,'v');a.link(155,125,155,152);a.node(155,171,210,l2,'s')
def ownership(a,i):
    for x,lab in [(75,"Cell A"),(232,"Cell B")]:a.node(x,58,97,lab,'s')
    a.link(76,75,136,112);a.link(230,75,176,112);a.node(155,132,153,"composed Cell",'s')
    if i:a.path([(75,76),(32,108),(32,177),(127,177)],c="#946422");a.node(201,178,142,"forward port",'v');a.link(201,162,179,150,c="#946422")
    else:a.txt(155,183,"keep both old owners",15)
def proof(a,i):
    if not i:chain(a,["proposal","replay primitives","verify output"],["n","v","v"])
    else:chain(a,["template + ports","instantiate macro","verify boundary"],["n","s","v"])

def visibility(a,i):
    a.node(66,55,86,"Run a","n");a.node(244,55,86,"Run b","n")
    a.link(112,55,198,55)
    if i==0:
        a.link(245,72,245,118);a.node(241,140,110,"publish B","s")
        a.txt(149,184,"compute B at its Run",16)
    else:
        a.link(65,72,65,109);a.node(78,130,144,"private B","s")
        a.path([(151,130),(231,130),(241,75)],c="#946422")
        a.txt(155,176,"exit: "+("primary fixed point" if i==1 else "integral fixed point"),15)
        for j in range(6):
            a.rect(64+31*j,187,26,10,"#a7c8d7" if j<3 else ("white" if i==1 else "#afdad1"),"#71878e",2,i==1 and j>=3)
def stopping(a,i):
    chain(a,["frontier",["fixed round budget","exact worklist","learned stop gate"][i],["return at K","stop if empty","defer or audit"][i]],
          ["n","v" if i==1 else "n","v"])
def template_classes(a,mode):
    # p and q have a certified local equality after effect k; r has none.
    xs=(57,155,252)
    a.txt(155,36,"template T  /  after step k",14)
    for x,l in zip(xs,"pqr"):a.port(x,80,l)
    if mode==0:
        a.txt(155,143,"read / test / copy",17)
        a.txt(155,185,"baseline port graph",14,SUB)
    elif mode==1:
        for x,lab in zip(xs,("C1","C2","C3")):
            a.link(x,98,x,134);a.node(x,154,55,lab,'v')
        a.txt(155,196,"one class per port",14,SUB)
    elif mode==2:
        a.path([(57,99),(57,130),(155,130),(155,99)],c="#946422")
        a.txt(105,157,"proven equal",15)
        a.txt(155,196,"pairwise relation edges",14,SUB)
    else:
        for x,end in [(57,92),(155,120),(252,252)]:a.link(x,99,end,134,c="#946422")
        a.node(107,154,75,"Cpq",'v');a.node(252,154,55,"Cr",'v')
        a.txt(155,196,"port–class incidence",14,SUB)

def plate(name,arms,fn):
    W,H=1100,294
    a=Art();a.rect(0,0,W,H,"#f5f7f7",r=0)
    step=(W-20)/len(arms)
    for i,(lab,arg) in enumerate(arms):
        left=10+i*step
        a.rect(left+3,7,step-6,H-14,"#fff","#d4dfe0",9)
        a.txt(left+18,37,chr(97+i),20,"#236960","start",True)
        a.txt(left+41,37,lab,18,INK,"start",True)
        scale=min(1.10,(step-18)/310)
        a.put(f'<g transform="translate({left+(step-310*scale)/2:.1f} 49) scale({scale:.4f})">');fn(a,arg);a.put('</g>')
    write(name,a,W,H)

def write(name,a,w,h):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img"><title>{escape(name)}</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{LINE}"/></marker></defs>'+''.join(a.e)+'</svg>\n'
    (OUT/(name+'.svg')).write_text(svg)

def overview():
    a=Art();W,H=1100,330;a.rect(0,0,W,H,BG,r=0)
    for x,w,l,c in [(12,221,"OFFLINE  /  EggFuse","#247568"),(246,604,"ONLINE  /  PyTorch GPU","#305e81"),(863,225,"POST-RUN  /  audit","#946422")]:
        a.rect(x,12,w,306,"#fff","#ccdada",8);a.txt(x+15,43,l,17,c,"start",True)
    a.node(122,105,162,"scheduled .egg","s");a.link(122,124,122,169);a.node(122,190,164,"plan.json","s")
    a.path([(205,190),(258,190),(258,115),(287,115)])
    a.path([(258,190),(279,190),(279,62),(701,62),(701,96)],c="#247568")
    a.txt(506,58,"shared static routes",13,SUB)
    a.node(350,115,120,"make");a.node(737,115,130,"finish")
    a.txt(350,84,"A + B",17);a.txt(737,84,"Request",17)
    a.link(411,115,464,115);a.grid(477,79,4,2,cell=15,dy=4);a.link(522,115,667,115)
    a.txt(557,176,"generated Pair · 8 × 90",18)
    a.rect(341,202,250,38,*PALETTE["n"],r=4);a.txt(466,226,"64 continuous",17)
    a.rect(594,202,193,38,*PALETTE["s"],r=4);a.txt(690,226,"26 categorical",17)
    a.txt(557,269,"row × position  •  activation, parent refs, fields",16,SUB)
    a.link(804,115,898,115);a.node(974,115,140,"Result set","v");a.link(974,134,974,187);a.node(974,205,160,"lineage + cover","v")
    a.txt(974,249,"duplicates / missing",15,SUB);a.txt(122,254,"typed port routes",15,SUB)
    write("00-overview",a,W,H)

PLATES=[
("01-template",[("Template ID",0),("Compiler roles",1),("Pooled GNN",2),("Port GNN",3)],graph),
("02-heads",[("One head per rule",False),("One head across rules",True)],heads),
("03-address",[("Flat coordinate",0),("Two rotary axes",1),("Add port axis",2),("Packed address",3)],address),
("04-width",[("Single row",1),("Two rows",2),("Four rows",4)],width),
("05-learning",[("Zero-shot",0),("Set supervision",1),("Team RL",2),("Counterfactual RL",3)],curriculum),
("06-gates",[("Fixed active rows",False),("Learned activation",True)],gate),
("07-ready",[("Global barrier","barrier"),("Dependency readiness","local"),("Learned readiness","predict")],ready),
("08-projection",[("Predict fields",0),("Static projection",1),("Projection + aux head",2)],projection),
("09-parents",[("All channels",0),("Hide parents",1),("Hide parents + latent",2)],tokenmask),
("10-recurrence",[("Continuous frontier",False),("Typed frontier",True)],recurrence),
("11-allocation",[("One anchor per slot",0),("Free slots, joint",1),("Free slots, row-local",2)],allocate),
("12-coverage",[("Set loss",False),("Set loss + coverage",True)],coverage),
("13-history",[("Blinded history",0),("All rows",1),("Same row only",2)],history),
("14-locality",[("Global state",0),("Local states + messages",1),("Certified port path",2)],locality),
("15-union",[("Eager equality",0),("Deferred equality",1)],union),
("16-owner",[("Retain instances",0),("Transfer + forwarding",1)],ownership),
("17-proof",[("Primitive witness",0),("Composed witness",1)],proof),
("18-integral",[("Original schedule",0),("Primary exit",1),("Integral exit",2)],visibility),
("19-stop",[("Fixed rounds",0),("Exact worklist",1),("Learned gate",2)],stopping),
("20-template-classes",[("Explicit ports",0),("Singletons",1),("Pairwise Eq",2),("Class nodes",3)],template_classes)]
def synthesis():
    a=Art();W,H=1100,335;a.rect(0,0,W,H,BG,r=0)
    for x,w,h in [(10,316,"SHARED TEMPLATE"),(338,374,"INSTANCE POLICY"),(723,367,"JOINT OUTCOME")]:
        a.rect(x,8,w,317,"#fff","#d2dddd",8);a.txt(x+15,38,h,17,INK,"start",True)
    for x,t in [(64,"Pair"),(228,"Request")]:a.txt(x,80,t,17)
    for x,y,l in [(64,108,"i"),(64,163,"x"),(228,108,"i"),(228,163,"t")]:a.port(x,y,l)
    a.link(82,108,208,108,c="#247568");a.txt(146,99,"equal",14)
    a.path([(147,111),(147,146),(162,146),(162,191)],c="#247568")
    a.path([(65,180),(65,210),(130,210)],c="#247568");a.path([(228,180),(228,210),(196,210)],c="#247568")
    a.node(162,210,75,"GNN","s");a.txt(167,262,"one embedding per port",18)
    a.path([(202,210),(313,210),(313,120),(413,120)])
    a.node(525,72,225,"live tokens + parent refs","n");a.link(525,89,525,102)
    a.node(525,121,213,"shared pointer policy","n")
    for yy in [187,240]:
        a.path([(526,140),(526,yy),(565,yy)])
        a.grid(573,yy-10,1,3,cell=18,dx=4)
    a.txt(411,192,"row 0",18);a.txt(411,245,"row 1",18)
    a.path([(642,187),(701,187),(701,127),(765,127)])
    a.path([(642,240),(701,240),(701,142),(765,142)])
    a.node(890,136,244,"actual generated binding set","w")
    a.link(890,154,890,195,dash=True,c="#775692");a.node(890,215,220,"audit → reward / critic","t")
    a.path([(778,216),(754,216),(754,286),(508,286),(508,141)],dash=True,c="#775692")
    a.txt(889,265,"training only",15,SUB);a.txt(526,309,"actor updates",15,SUB)
    write("00-proposal",a,W,H)

def paired_results():
    a=Art();W,H=1100,235;a.rect(0,0,W,H,BG,r=0)
    a.txt(24,31,"FINISH  /  COMPLETE NONEMPTY GRAPHS",18,INK,"start",True)
    a.txt(716,30,"seed 1703",15,anchor="start");a.port(693,25,"","s")
    a.txt(909,30,"seed 1709",15,anchor="start");a.rect(883,15,17,17,*PALETTE["n"],r=1)
    x=lambda n:270+n*9.4
    for n in range(0,81,10):
        a.path([(x(n),50),(x(n),188)],c="#dce5e4",arrow=False);a.txt(x(n),214,n,15,SUB)
    for y,label,p,q in [(78,"Field head",49,41),(124,"Static projection",39,37),(170,"Projection + auxiliary",65,67)]:
        a.txt(32,y+6,label,19,INK,"start")
        a.path([(x(p),y),(x(q),y)],c="#8197a1",arrow=False)
        a.put(f'<circle cx="{x(p)}" cy="{y}" r="7" fill="#d9efea" stroke="#247568" stroke-width="2.5"/>')
        a.rect(x(q)-6,y-6,12,12,*PALETTE["n"],r=0)
        a.txt(min(x(p),x(q))-14,y+5,min(p,q),15,anchor="end")
        a.txt(max(x(p),x(q))+14,y+5,max(p,q),15,anchor="start")
    write("00-results",a,W,H)

if __name__=="__main__":
    OUT.mkdir(exist_ok=True);overview();synthesis();paired_results()
    for name,arms,fn in PLATES:plate(name,arms,fn)
