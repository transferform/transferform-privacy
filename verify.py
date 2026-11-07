import json, pathlib, tempfile, zipfile, traceback
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).parent
out=root/"evidence";out.mkdir(exist_ok=True)
results=[]
with sync_playwright() as p:
 for name in ("module-a","module-b","module-c"):
  row={"file":name+".zip","loaded":False,"popup":None,"form_page":False,"errors":[]}
  try:
   with tempfile.TemporaryDirectory() as tmp:
    ext=pathlib.Path(tmp)/"extension";ext.mkdir()
    with zipfile.ZipFile(root/(name+".zip")) as z:z.extractall(ext)
    manifest=json.loads((ext/"manifest.json").read_text(encoding="utf-8-sig"))
    row["version"]=manifest["version"]
    context=p.chromium.launch_persistent_context(str(pathlib.Path(tmp)/"profile"),channel="chromium",headless=True,args=[f"--disable-extensions-except={ext}",f"--load-extension={ext}"])
    try:
     page=context.new_page()
     page.goto("chrome://extensions/",wait_until="domcontentloaded")
     page.screenshot(path=str(out/(name+"-manager.png")))
     workers=[w.url for w in context.service_workers]
     ids=page.evaluate("""() => {const m=document.querySelector('extensions-manager')?.shadowRoot; const l=m?.querySelector('extensions-item-list')?.shadowRoot; return [...(l?.querySelectorAll('extensions-item')||[])].map(e=>e.id).filter(Boolean)}""")
     row["workers"]=workers
     row["extension_ids"]=ids
     row["loaded"]=bool(workers or ids)
     extension_id=workers[0].split("/")[2] if workers else (ids[0] if ids else None)
     popup=manifest.get("action",{}).get("default_popup")
     if popup and extension_id:
      pp=context.new_page()
      pp.goto("chrome-extension://"+extension_id+"/"+popup.lstrip("/"),wait_until="domcontentloaded",timeout=15000)
      row["popup"]=pp.url
      pp.screenshot(path=str(out/(name+"-popup.png")))
     form=context.new_page()
     form.goto("data:text/html,<html><body><form><input name='name' value='Alice'><input name='email' value='alice@example.com'><input name='phone' value='11999999999'></form></body></html>")
     row["form_page"]=form.locator("input").count()==3
    finally:context.close()
  except Exception as e:row["errors"].append(str(e))
  results.append(row)
(out/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
if not all(r["loaded"] for r in results):raise SystemExit(1)
