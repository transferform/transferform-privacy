import json, pathlib, tempfile, zipfile, traceback, subprocess, os, time
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
    row["manifest_permissions"]=manifest.get("permissions",[])
    row["host_permissions"]=manifest.get("host_permissions",[])
    row["version"]=manifest["version"]
    context=p.chromium.launch_persistent_context(str(pathlib.Path(tmp)/"profile"),channel="chromium",headless=False,args=[f"--disable-extensions-except={ext}",f"--load-extension={ext}"])
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

     if name=="module-a" and extension_id:
      row["test_mode"]="headed chromium under Xvfb, genuine browser toolbar activation"
      try:
       page.goto("chrome://extensions/shortcuts")
       page.screenshot(path=str(out/"shortcuts.png"))
      except Exception as e:row["shortcut_error"]=str(e)

      import http.server,threading
      class Handler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers()
        if self.path.startswith("/source"):
         fields=[("Nome completo","nome","Maria Silva"),("E-mail","email","maria@example.com"),("Telefone","telefone","31999998888"),("CPF","cpf","12345678901"),("CEP","cep","36010000"),("Cargo","cargo","Analista")]
        else:
         fields=[("Nome completo","nome",""),("E-mail","email",""),("Telefone","telefone",""),("CPF","cpf",""),("CEP","cep",""),("Cargo","cargo","")]
        html="<html><body><form>"+ "".join('<label>'+label+'<input name="'+key+'" id="'+key+'" value="'+val+'"></label>' for label,key,val in fields)+"</form></body></html>"
        self.wfile.write(html.encode())
       def log_message(self,*args):pass
      server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
      threading.Thread(target=server.serve_forever,daemon=True).start()
      try:
       source=context.new_page();source.goto(f"http://127.0.0.1:{server.server_port}/source")
       source.bring_to_front()
       source.bring_to_front()
       source.keyboard.press("Control+Shift+Y")
       source.wait_for_timeout(350)
       capture=context.new_page();capture.goto(f"chrome-extension://{extension_id}/popup.html")
       capture.locator("#captureBtn").click()
       capture.wait_for_timeout(600)
       row["capture_status"]=capture.locator("#captureStatus").inner_text()
       capture.close()
       target=context.new_page();target.goto(f"http://127.0.0.1:{server.server_port}/target")
       target.bring_to_front()
       match=context.new_page();match.goto(f"chrome-extension://{extension_id}/popup.html")
       match.locator("#prepareBtn").click()
       match.wait_for_timeout(900)
       row["match_status"]=match.locator("#matchStatus").inner_text()
       row["match_count"]=match.locator("#matchCount").inner_text()
       row["apply_enabled"]=match.locator("#applyBtn").is_enabled()
       if row["apply_enabled"]:
        match.locator("#applyBtn").click()
        match.wait_for_timeout(600)
        row["apply_status"]=match.locator("#applyStatus").inner_text()
       row["target_values"]=target.locator("input").evaluate_all("(els)=>Object.fromEntries(els.map(x=>[x.name,x.value]))")
       row["functional_correct"]=all(row["target_values"].get(k)==v for k,v in {"nome":"Maria Silva","email":"maria@example.com","telefone":"31999998888","cpf":"12345678901","cep":"36010000","cargo":"Analista"}.items())
       match.screenshot(path=str(out/(name+"-functional.png")))
      finally:server.shutdown()
    finally:context.close()
  except Exception as e:row["errors"].append(str(e))
  results.append(row)
(out/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
if not all(r["loaded"] for r in results):raise SystemExit(1)
