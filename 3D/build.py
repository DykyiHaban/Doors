import json,os
d=os.path.dirname(os.path.abspath(__file__))
data={k:json.load(open(os.path.join(d,"board3d_%s.json"%k))) for k in ("stm32","tg")}
t=open(os.path.join(d,"viewer.template.html"),encoding="utf-8").read().replace("/*DATA*/",json.dumps(data,separators=(",",":")))
open(os.path.join(d,"viewer.html"),"w",encoding="utf-8").write(t)
