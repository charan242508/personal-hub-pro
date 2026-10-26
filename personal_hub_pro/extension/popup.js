// Local development API. Before publishing, replace this with your HTTPS production API.
const API_BASE = "http://127.0.0.1:5000";
const $ = (id) => document.getElementById(id);
const loginView = $("login-view");
const recordsView = $("records-view");
function status(message, error=false) {
  $("status").textContent = message;
  $("status").className = error ? "status error" : "status";
}
async function api(path, options={}) {
  const stored = await chrome.storage.session.get("accessToken");
  const headers = {"Content-Type":"application/json", ...(options.headers || {})};
  if (stored.accessToken) headers.Authorization = `Bearer ${stored.accessToken}`;
  const response = await fetch(API_BASE + path, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
async function showSignedOut() {
  loginView.hidden = false; recordsView.hidden = true;
}
async function loadRecords() {
  try {
    const me = await api("/api/me");
    $("user-email").textContent = me.email;
    const rows = await api("/api/records");
    $("records").replaceChildren();
    if (!rows.length) {
      const p = document.createElement("p"); p.className="hint"; p.textContent="No records yet."; $("records").append(p);
    }
    rows.forEach(record => {
      const card = document.createElement("div"); card.className="record";
      const name = document.createElement("strong"); name.textContent=record.full_name; card.append(name);
      [record.email, record.phone, `${record.category}${record.city ? " · "+record.city : ""}`].filter(Boolean).forEach(value => {
        const p=document.createElement("p"); p.textContent=value; card.append(p);
      });
      const del=document.createElement("button"); del.textContent="Delete record";
      del.addEventListener("click", async () => {
        if (!confirm(`Delete ${record.full_name}?`)) return;
        try { await api(`/api/records/${record.id}`, {method:"DELETE"}); await loadRecords(); status("Record deleted."); }
        catch(e){status(e.message,true);}
      });
      card.append(del); $("records").append(card);
    });
    loginView.hidden=true; recordsView.hidden=false; status("Connected securely to your account.");
  } catch (e) {
    await chrome.storage.session.remove("accessToken");
    await showSignedOut();
    status("Please sign in to continue.", true);
  }
}
$("login-form").addEventListener("submit", async e => {
  e.preventDefault(); status("Signing in…");
  try {
    const data=await api("/api/auth/login", {method:"POST", headers:{}, body:JSON.stringify({email:$("email").value,password:$("password").value})});
    await chrome.storage.session.set({accessToken:data.access_token});
    $("password").value="";
    await loadRecords();
  } catch(err) { status(err.message,true); }
});
$("add-form").addEventListener("submit", async e => {
  e.preventDefault();
  const payload={full_name:$("full_name").value,email:$("record-email").value,phone:$("phone").value,category:$("category").value,city:$("city").value,notes:$("notes").value};
  try { await api("/api/records",{method:"POST",body:JSON.stringify(payload)}); e.target.reset(); status("Record saved."); await loadRecords(); }
  catch(err){status(err.message,true);}
});
$("logout").addEventListener("click", async () => { await chrome.storage.session.remove("accessToken"); await showSignedOut(); status("Signed out."); });
$("open-site").addEventListener("click", () => chrome.tabs.create({url:API_BASE+"/"}));
$("open-dashboard").addEventListener("click", () => chrome.tabs.create({url:API_BASE+"/"}));
loadRecords();
