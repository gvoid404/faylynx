#!/usr/bin/env python3
"""Train the two gateway models and export them as plain JSON for the stdlib-only server.
  content: TF-IDF(word 1-2gram) + LogisticRegression, 3 classes; prompt-bank items are held out.
  actor:   XGBoost on the 7 style-invariant behavioral features (human vs agent).
Extra labeled rows (e.g. live captures) can be added with --extra-content / --extra-actor."""
import argparse, json, math, re, pickle
from pathlib import Path
from collections import Counter
import numpy as np, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, StratifiedKFold
import xgboost as xgb
HARD=["inter_key_cv","dwell_cv","mouse_straightness","prog_fill_ratio","paste_to_type_ratio","has_mouse","has_typing"]
KEEP={"Allow","Shadow AI","Automated AI Pipelines"}
ap=argparse.ArgumentParser()
ap.add_argument("--p2",default="..",help="paper2-three-class folder (holds data/ and results/)")
ap.add_argument("--bank",default="prompt_bank.json")
ap.add_argument("--actor-csv",nargs="+",default=["results/sessions_features.csv","results/fusion_sessions.csv"])
ap.add_argument("--extra-content",nargs="*",default=[],help="jsonl with prompt,label")
ap.add_argument("--extra-actor",nargs="*",default=[],help="csv with HARD features + label(human/agent)")
ap.add_argument("--include-bank",action="store_true",help="do not hold the prompt bank out (final refined model)")
ap.add_argument("--out",default="models"); ap.add_argument("--tag",default="v3")
a=ap.parse_args(); P2=Path(a.p2); out=Path(a.out); out.mkdir(exist_ok=True)
bank=json.load(open(a.bank)); held=set() if a.include_bank else {b["source_id"] for b in bank["prompts"]}
norm=lambda t: re.sub(r"\s+"," ",t.strip())
heldtxt=set() if a.include_bank else {norm(b["type_text"]+("\n\n"+b["paste_text"] if b["paste_text"] else "")) for b in bank["prompts"]}
rows={}
srcs=[P2/"data/labeled/wildchat48m_full_10k_fable_v3_judged.jsonl",P2/"data/labeled/synthetic_shadow_v1.jsonl",P2/"data/gold/gold_consolidated_v1_text.jsonl",P2/"results/refine/train_refined.jsonl"]+[Path(x) for x in a.extra_content]
for s in srcs:
    if not s.exists(): continue
    for l in open(s,encoding="utf-8"):
        if not l.strip(): continue
        d=json.loads(l); lab=d.get("label"); t=(d.get("prompt") or "").strip()
        if lab in KEEP and len(t)>=15 and d.get("id") not in held and norm(t) not in heldtxt and d.get("gold_split")!="shadow_test":
            rows[t[:4000]]=lab
texts=list(rows); labels=list(rows.values())
vec=TfidfVectorizer(sublinear_tf=True,ngram_range=(1,2),min_df=2,max_features=30000)
X=vec.fit_transform(texts); clf=LogisticRegression(max_iter=3000,class_weight="balanced",C=4.0)
cv=cross_val_score(clf,X,labels,cv=StratifiedKFold(5,shuffle=True,random_state=7),scoring="f1_macro").mean()
clf.fit(X,labels)
# held-out prompt bank
bt=[b["type_text"]+("\n\n"+b["paste_text"] if b["paste_text"] else "") for b in bank["prompts"]]
bp=clf.predict(vec.transform(bt)); by={}
for b,p in zip(bank["prompts"],bp): by.setdefault(b["class"],[]).append(p==b["class"])
bank_acc={k:round(float(np.mean(v)),3) for k,v in by.items()}
terms=vec.get_feature_names_out(); idf=vec.idf_; coef=clf.coef_
cj={"type":"tfidf_lr","tag":a.tag,"classes":list(clf.classes_),"intercept":[round(float(x),5) for x in clf.intercept_],
    "terms":{t:[round(float(idf[i]),4)]+[round(float(c),4) for c in coef[:,i]] for i,t in enumerate(terms)},
    "n_train":len(texts),"train_counts":dict(Counter(labels)),"cv5_macro_f1":round(float(cv),4),"bank_holdout_acc":bank_acc}
json.dump(cj,open(out/"content_model.json","w"))
pickle.dump({"vectorizer":vec,"classifier":clf,"classes":list(clf.classes_),"n_train":len(texts)},open(out/f"content_channel_{a.tag}.pkl","wb"))
# ---- actor ----
fr=[]
for p in a.actor_csv+a.extra_actor:
    if not Path(p).exists(): continue
    d=pd.read_csv(p); lab=d["label"] if "label" in d else d["true_actor"]
    x=d[HARD].copy(); x["y"]=(lab=="agent").astype(int).values; fr.append(x)
D=pd.concat(fr,ignore_index=True); Xa=D[HARD].astype(float).replace([np.inf,-np.inf],np.nan); ya=D["y"].values
m=xgb.XGBClassifier(n_estimators=200,max_depth=3,learning_rate=0.1,subsample=0.9,colsample_bytree=0.9,eval_metric="logloss",random_state=20261107,base_score=0.5)
acv=cross_val_score(m,Xa,ya,cv=StratifiedKFold(5,shuffle=True,random_state=7)).mean(); m.fit(Xa,ya)
trees=[json.loads(t) for t in m.get_booster().get_dump(dump_format="json")]
aj={"type":"xgb_trees","tag":a.tag,"features":HARD,"base_margin":0.0,"trees":trees,"n_train":int(len(D)),"n_agent":int(ya.sum()),"cv5_acc":round(float(acv),4)}
json.dump(aj,open(out/"actor_model.json","w"))
m.save_model(str(out/f"actor_{a.tag}.xgb.json"))
print(f"content: n={len(texts)} {dict(Counter(labels))} cv_macroF1={cv:.3f} bank_holdout={bank_acc}")
print(f"actor: n={len(D)} agent={int(ya.sum())} cv_acc={acv:.3f}")
