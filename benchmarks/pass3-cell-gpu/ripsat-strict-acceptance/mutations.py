"""Single-fault changes to real Get/Single artifacts. All cardinalities used by legacy RipSat checks are preserved."""
import json


def edit(path, apply):
    data=json.loads(path.read_bytes())
    before=json.dumps(data,sort_keys=True)
    apply(data)
    assert before!=json.dumps(data,sort_keys=True),path
    path.write_text(json.dumps(data,indent=1,ensure_ascii=False,allow_nan=False)+"\n")
    return [path]


def stopped(report):
    report["ripen"]["state"]="ObservedUnfinished"
    report["native_stop_reason"]="test resource limit"


def observation_only(graph):
    graph["scope"]["observation_only"]=True


def foreign_swapped_row(graph):
    row,=[r for r in graph["rows"] if r["op"]=="Single"]
    before=row["args"][0];sort=graph["values"][before]["sort"]
    replacement=next(i for i,v in enumerate(graph["values"]) if v["sort"]==sort and i!=before)
    row["args"][0]=replacement


def unexpected_local_alias(graph):
    src=graph["ports"]["input_0_c0"]
    alternate=graph["ports"]["input_0"]
    assert src!=alternate and graph["values"][src]["sort"]==graph["values"][alternate]["sort"]
    graph["ports"]["input_0_c0"]=alternate


def foreign_grounded_program(report):
    text=report["source_text"]
    assert "Single" in text
    report["source_text"]=text.replace("Single","ForeignSingle")


def missing_named_input(origin):
    sample=origin["sample"]; named=[r for r in sample["producer"]["rows"] if r.get("named") is not None]
    assert named
    # Value/sort data remain, but the neural issuer never named this physical source.
    atom=named[0]["atom"]
    named[0]["named"]=None
    for row in origin["profile"]["root_rows"]:
        if row["atom"]==atom:row["named"]=None


def wrong_source_op(origin):
    sample=origin["sample"]
    # A plausible nonnegative position on a different effect does not authorize
    # the source constructor whose recorded physical FactRef still has the old op.
    sample["producer_op"]+=1


def wrong_source_run(origin):
    sample=origin["sample"]
    assert sample["producer"]["epoch"]<sample["consumer"]["epoch"]
    sample["consumer"]["epoch"]=sample["producer"]["epoch"]
    sample["relative_runs"]=0


def wrong_origin_version(origin):
    sample=origin["sample"]
    row=next(r for r in sample["consumer"]["rows"] if r["atom"]==sample["consumer_atom"])
    assert row["named"]["version"]==sample["original_version"]
    row["named"]["version"]+=1


def coherent_wrong_op(origin):
    sample=origin["sample"]
    original=sample["original_fact"]
    replacement=(original&~0xffffffff)|(sample["producer_op"]+1)
    target=next(r for r in sample["consumer"]["rows"] if r["atom"]==sample["consumer_atom"])
    assert target["named"]["row"]["Fact"]["op"]==sample["producer_op"]
    sample["producer_op"]+=1
    target["named"]["row"]["Fact"]["op"]=sample["producer_op"]
    sample["original_fact"]=replacement
    sample["birth_event"][4]=replacement


def missing_native_application(history):
    assert history["records"]
    history["records"]=[]
    for boundary in history["boundaries"]:
        boundary["end"]=0


def wrong_native_read_dependency(history):
    record=history["records"][0]
    assert record["required"]
    # A real native history token of the same sample; substituting its identity
    # changes the external read obligation while retaining a plausible history.
    token=record["required"][0]
    replacement=next((i for i,t in enumerate(history["tokens"]) if i!=token and t["sort"]==history["tokens"][token]["sort"]),next(i for i in range(len(history["tokens"])) if i!=token))
    record["required"][0]=replacement


def foreign_ground_literal(graph):
    literals=[value for value in graph["values"] if value["sort"]=="i64" and value["literal"]=="0"]
    assert len(literals)==1
    literals[0]["literal"]="37"


def producer_scope_only(origin):
    assert origin["profile"]["scope_mode"]=="full"
    origin["profile"]["scope_mode"]="producer"


def unfinished_round(report):
    assert report["ripen"]["state"]=="Saturated"
    report["ripen"]["updated"]=True


def wrong_produced_class(history):
    record=history["records"][0]
    pair=next((col,tok) for col,tok in zip(record["outputs"],record["values"])
              if isinstance(col,dict) and "Column" in col and col["Column"][1]==0)
    tid=pair[1];tokens=history["tokens"];old=tokens[tid]
    other=next(x["final_class"] for x in tokens if x["sort"]==old["sort"]
               and x.get("final_class") is not None and x["final_class"]!=old["final_class"])
    old["final_class"]=other


def disconnected_native_applications(history):
    producer,consumer,*_=history["records"]
    # "parents" are dense positions in the native history, unlike record id 8.
    assert producer["id"]==0 and consumer["id"]==8 and 0 in consumer["parents"]
    consumer["parents"]=[p for p in consumer["parents"] if p!=0]


def wrong_consumer_native_read(history):
    producer,consumer,*_=history["records"]
    inherited=set(producer["produced"]) & set(consumer["required"])
    assert len(inherited)==1
    expected=next(iter(inherited))
    replacement=len(history["tokens"])
    clone=dict(history["tokens"][expected]);clone["external"]=True
    history["tokens"].append(clone)
    consumer["required"]=[replacement if value==expected else value for value in consumer["required"]]


def wrong_but_later_source_run(origin):
    sample=origin["sample"]
    sample["consumer"]["epoch"]+=1
    sample["relative_runs"]=sample["consumer"]["epoch"]-sample["producer"]["epoch"]
