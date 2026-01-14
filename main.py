<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Lexia360 · Legal inmobiliario, claro y rápido</title>

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css" />

  <style>
    :root{
      --bg:#0b1220;
      --card:#ffffff;
      --muted:#667085;
      --brand:#0b5fff;
      --brand2:#5b8cff;
      --border:#e6e8ef;
    }

    body{
      margin:0;
      background:
        radial-gradient(1000px 500px at 20% 0%, rgba(11,95,255,.25), transparent 55%),
        radial-gradient(900px 520px at 90% 10%, rgba(91,140,255,.18), transparent 60%),
        linear-gradient(180deg, #0b1220 0%, #0f1a33 60%, #f6f7fb 60%, #f6f7fb 100%);
    }

    .nav{
      position:sticky; top:0; z-index:20;
      backdrop-filter: blur(10px);
      background: rgba(11,18,32,.55);
      border-bottom: 1px solid rgba(255,255,255,.10);
    }

    .wrap{ max-width:1100px; margin:0 auto; padding:16px 18px; }

    .nav-row{ display:flex; justify-content:space-between; align-items:center; gap:12px; }

    .logo{
      display:flex; align-items:center; gap:10px;
      color:#fff; text-decoration:none; font-weight:900; letter-spacing:.2px;
    }

    .logo-badge{
      width:34px;height:34px;border-radius:10px;
      background: linear-gradient(135deg, var(--brand) 0%, var(--brand2) 100%);
      display:flex; align-items:center; justify-content:center;
      box-shadow: 0 10px 18px rgba(11,95,255,.22);
    }

    .nav-actions{ display:flex; gap:10px; flex-wrap:wrap; }

    .btn{
      border:1px solid rgba(255,255,255,.18);
      background: rgba(255,255,255,.06);
      color:#fff;
      padding:10px 14px;
      border-radius:12px;
      font-weight:900;
      cursor:pointer;
    }
    .btn.primary{
      background: linear-gradient(135deg, var(--brand) 0%, var(--brand2) 100%);
      border-color: transparent;
    }

    .hero{ padding:44px 18px 26px; }
    .hero-grid{
      max-width:1100px; margin:0 auto;
      display:grid; grid-template-columns:1.2fr .8fr; gap:22px;
      align-items:start;
    }
    @media(max-width:900px){ .hero-grid{ grid-template-columns:1fr; } }

    .headline{ color:#fff; font-size:40px; line-height:1.05; margin:0 0 12px; font-weight:900; }
    .sub{ color: rgba(255,255,255,.78); font-size:16px; margin:0 0 18px; }

    .trust{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
    .pill{
      font-size:12px; color: rgba(255,255,255,.85);
      border:1px solid rgba(255,255,255,.16);
      background: rgba(255,255,255,.06);
      padding:6px 10px; border-radius:999px;
    }

    .card{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 18px 40px rgba(16,24,40,.10);
    }

    .card h3{ margin:0 0 8px; }
    .muted{ color: var(--muted); font-size:13px; }

    input{ border-radius:12px !important; }
    button{ border-radius:12px !important; font-weight:900 !important; }

    .section{ padding:26px 18px 60px; }

    .features{
      max-width:1100px; margin:0 auto;
      display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
    }
    @media(max-width:900px){ .features{ grid-template-columns:1fr; } }

    .feat{
      background:#fff; border:1px solid var(--border);
      border-radius:16px; padding:16px;
    }
    .feat b{ display:block; margin-bottom:6px; }

    footer{
      max-width:1100px; margin:0 auto;
      padding:20px 18px 40px;
      color:#98a2b3; font-size:12px;
    }

    .error{ color:#b42318; font-size:13px; margin-top:8px; }
    .ok{ color:#027a48; font-size:13px; margin-top:8px; }

    .links{ display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; }
    .links a{ color:#98a2b3; text-decoration:none; }
    .links a:hover{ text-decoration:underline; }
  </style>
</head>

<body>
  <div class="nav">
    <div class="wrap nav-row">
      <a class="logo" href="/static/index.html" title="Inicio">
        <div class="logo-badge"><span>⚖️</span></div>
        <div>Lexia360</div>
      </a>

      <div class="nav-actions">
        <button class="btn" onclick="show('login')">Iniciar sesión</button>
        <button class="btn primary" onclick="show('register')">Crear cuenta</button>
      </div>
    </div>
  </div>

  <section class="hero">
    <div class="hero-grid">
      <div>
        <h1 class="headline">Legal inmobiliario,<br>claro y rápido.</h1>
        <p class="sub">
          Crea fichas de inmuebles, ejecuta reglas básicas, identifica zona tensionada (según dataset)
          y descarga un informe PDF profesional.
        </p>

        <div class="trust">
          <span class="pill">✅ Ficha por inmueble</span>
          <span class="pill">✅ Informe PDF</span>
          <span class="pill">✅ Papelera (borrado seguro)</span>
          <span class="pill">🔒 Pro (próximo)</span>
        </div>
      </div>

      <div class="card">
        <section id="loginBox">
          <h3>Accede</h3>
          <div class="muted">Entra al panel y gestiona tus inmuebles.</div>

          <label>Email</label>
          <input id="loginEmail" type="email" placeholder="tucorreo@..." />

          <label>Contraseña</label>
          <input id="loginPassword" type="password" placeholder="••••••••" />

          <button onclick="login()" class="primary">Entrar</button>
          <div id="loginMsg" class="error"></div>
        </section>

        <section id="registerBox" style="display:none;">
          <h3>Crear cuenta</h3>
          <div class="muted">Crea tu cuenta en 30 segundos.</div>

          <label>Nombre</label>
          <input id="regNombre" type="text" placeholder="Nombre y apellidos" />

          <label>Email</label>
          <input id="regEmail" type="email" placeholder="tucorreo@..." />

          <label>Contraseña</label>
          <input id="regPassword" type="password" placeholder="mínimo 8 caracteres" />

          <button onclick="register()" class="primary">Crear cuenta</button>
          <div id="regMsg" class="error"></div>
        </section>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="features">
      <div class="feat">
        <b>📌 Fichas por inmueble</b>
        <div class="muted">Cada inmueble tiene diagnóstico y semáforo (MVP).</div>
      </div>
      <div class="feat">
        <b>📄 Informe PDF</b>
        <div class="muted">Un informe presentable para archivo o cliente.</div>
      </div>
      <div class="feat">
        <b>🧠 Asistente (MVP)</b>
        <div class="muted">General gratis. Caso concreto: Pro.</div>
      </div>
    </div>
  </section>

  <footer>
    © 2026 Lexia360 · Todos los derechos reservados
    <div class="links">
      <a href="#">Aviso legal</a>
      <a href="#">Privacidad</a>
      <a href="#">Contacto</a>
    </div>
  </footer>

  <script>
    const apiUrl = location.origin;

    (async()=>{
      const token = localStorage.getItem("token");
      if(!token) return;
      try{
        const res = await fetch(`${apiUrl}/me`, { headers:{ "Authorization": `Bearer ${token}` }});
        if(res.ok) window.location.href="/static/dashboard.html";
        else localStorage.removeItem("token");
      }catch(e){}
    })();

    function show(which){
      document.getElementById("loginBox").style.display = which === "login" ? "block" : "none";
      document.getElementById("registerBox").style.display = which === "register" ? "block" : "none";
      document.getElementById("loginMsg").textContent = "";
      document.getElementById("regMsg").textContent = "";
    }

    async function register(){
      const nombre = document.getElementById("regNombre").value.trim();
      const email = document.getElementById("regEmail").value.trim();
      const password = document.getElementById("regPassword").value;

      const msg = document.getElementById("regMsg");
      msg.className = "error";
      msg.textContent = "";

      try{
        const res = await fetch(`${apiUrl}/register`, {
          method:"POST",
          headers:{ "Content-Type":"application/json" },
          body: JSON.stringify({ nombre, email, password })
        });
        const data = await res.json().catch(()=>({}));

        if(!res.ok){
          msg.textContent = data.detail || "Error al registrar.";
          return;
        }

        msg.className = "ok";
        msg.textContent = "✅ Cuenta creada. Ahora inicia sesión.";
        setTimeout(()=>show("login"), 800);

      }catch(e){
        msg.textContent = "⚠️ No se pudo conectar con el servidor.";
      }
    }

    async function login(){
      const email = document.getElementById("loginEmail").value.trim();
      const password = document.getElementById("loginPassword").value;

      const msg = document.getElementById("loginMsg");
      msg.className = "error";
      msg.textContent = "";

      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      try{
        const res = await fetch(`${apiUrl}/token`, { method:"POST", body: formData });
        const data = await res.json().catch(()=>({}));

        if(data.access_token){
          localStorage.setItem("token", data.access_token);
          localStorage.setItem("email", email.toLowerCase().trim());
          window.location.href = "/static/dashboard.html";
        }else{
          msg.textContent = data.detail || "❌ Credenciales incorrectas.";
        }
      }catch(e){
        msg.textContent = "⚠️ No se pudo conectar con el servidor.";
      }
    }
  </script>
</body>
</html>
