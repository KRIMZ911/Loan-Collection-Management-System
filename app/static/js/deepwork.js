/* ============================================================
 *  Deep Work Mode — БПҮХ Call Center Engine
 *  Keyboard-driven, one-case-at-a-time workflow
 * ============================================================ */

const DeepWork = {

  // ── State ──
  cases: [],
  currentIndex: 0,
  page: 1,
  level: 1,           // 1=what happened, 2=what they said, 3=when pay
  isActive: false,
  notes: "",
  stats: { called: 0, reached: 0, promises: 0, paid: 0, sms: 0, skipped: 0 },

  // ── Init ──
  init() {
    this.page = 1;
    this.currentIndex = 0;
    this.level = 1;
    this.notes = "";
    this.stats = { called: 0, reached: 0, promises: 0, paid: 0, sms: 0, skipped: 0 };
    this.loadBatch(1);
  },

  loadBatch(page) {
    this.page = page;
    fetch(`/api/deepwork/queue?page=${page}`)
      .then(r => r.json())
      .then(data => {
        if (!data.cases || data.cases.length === 0) {
          this.showEmpty();
          return;
        }
        this.cases = data.cases;
        this.currentIndex = 0;
        this.isActive = true;
        this.level = 1;
        this.showOverlay();
        this.renderCard();
        this.attachKeys();
      })
      .catch(e => { alert("Алдаа: " + e.message); });
  },

  // ── Overlay ──
  showOverlay() {
    let ov = document.getElementById("dwOverlay");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "dwOverlay";
      ov.className = "dw-overlay";
      document.body.appendChild(ov);
    }
    ov.style.display = "flex";
    document.body.style.overflow = "hidden";
  },

  hideOverlay() {
    const ov = document.getElementById("dwOverlay");
    if (ov) ov.style.display = "none";
    document.body.style.overflow = "";
  },

  // ── Keyboard ──
  _keyHandler: null,

  attachKeys() {
    if (this._keyHandler) document.removeEventListener("keydown", this._keyHandler);
    this._keyHandler = (e) => this.handleKey(e);
    document.addEventListener("keydown", this._keyHandler);
  },

  detachKeys() {
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  },

  handleKey(e) {
    // Don't capture if typing in notes
    if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") {
      if (e.key === "Escape") { e.target.blur(); this.level = 1; this.renderCard(); }
      return;
    }
    if (!this.isActive) return;

    const k = e.key;

    if (this.level === 1) {
      if (k === "1") this.action_noAnswer();
      else if (k === "2") { this.level = 2; this.renderCard(); }
      else if (k === "3") this.action_wrongNumber();
      else if (k === "4") this.action_smsSent();
      else if (k === " ") { e.preventDefault(); this.action_skip(); }
      else if (k === "Escape") this.exit();
    }
    else if (this.level === 2) {
      if (k === "1") { this.level = 3; this.renderCard(); }
      else if (k === "2") this.action_paid();
      else if (k === "3") this.action_infoGiven();
      else if (k === "4") this.action_dispute();
      else if (k === "5") this.action_other();
      else if (k === "Escape") { this.level = 1; this.renderCard(); }
    }
    else if (this.level === 3) {
      const today = new Date();
      if (k === "1") this.action_promise(this.fmtDate(today));
      else if (k === "2") { today.setDate(today.getDate()+1); this.action_promise(this.fmtDate(today)); }
      else if (k === "3") { const fri = new Date(); fri.setDate(fri.getDate()+(5-fri.getDay()+7)%7||7); this.action_promise(this.fmtDate(fri)); }
      else if (k === "4") { today.setDate(today.getDate()+7); this.action_promise(this.fmtDate(today)); }
      else if (k === "5") { const sal = new Date(); sal.setDate(25); if(sal<new Date()) sal.setMonth(sal.getMonth()+1); this.action_promise(this.fmtDate(sal)); }
      else if (k === "Escape") { this.level = 2; this.renderCard(); }
    }
  },

  fmtDate(d) { return d.toISOString().split("T")[0]; },

  // ── Actions ──
  action_noAnswer() {
    this.stats.called++;
    // SOUND_HOOK: play short blip
    this.saveAction({ contact_type: "phone_call", was_reached: false, outcome: "no_answer", notes: "" });
  },

  action_wrongNumber() {
    this.stats.called++;
    this.saveAction({ contact_type: "phone_call", was_reached: false, outcome: "wrong_number", notes: "" });
  },

  action_smsSent() {
    this.stats.sms++;
    // SOUND_HOOK: play swoosh
    this.saveAction({ contact_type: "sms", was_reached: false, outcome: "sms_sent", notes: "" });
  },

  action_skip() {
    this.stats.skipped++;
    // Move current case to end
    const c = this.cases.splice(this.currentIndex, 1)[0];
    this.cases.push(c);
    // SOUND_HOOK: play soft skip
    this.renderCard();
  },

  action_paid() {
    this.stats.called++; this.stats.reached++; this.stats.paid++;
    const n = this.getNotesValue();
    // SOUND_HOOK: play success chime
    this.saveAction({ contact_type: "phone_call", was_reached: true, outcome: "payment_made", notes: n });
  },

  action_infoGiven() {
    this.stats.called++; this.stats.reached++;
    const n = this.getNotesValue();
    this.saveAction({ contact_type: "phone_call", was_reached: true, outcome: "info_given", notes: n });
  },

  action_dispute() {
    this.stats.called++; this.stats.reached++;
    const n = this.getNotesValue();
    this.saveAction({ contact_type: "phone_call", was_reached: true, outcome: "dispute", notes: n || "Маргаантай" });
  },

  action_other() {
    this.stats.called++; this.stats.reached++;
    const n = this.getNotesValue();
    this.saveAction({ contact_type: "phone_call", was_reached: true, outcome: "other", notes: n });
  },

  action_promise(date) {
    this.stats.called++; this.stats.reached++; this.stats.promises++;
    const n = this.getNotesValue();
    // SOUND_HOOK: play positive ding
    this.saveAction({ contact_type: "phone_call", was_reached: true, outcome: "promise_made", notes: n, promised_date: date });
  },

  getNotesValue() {
    const ta = document.getElementById("dwNotes");
    return ta ? ta.value.trim() : "";
  },

  // ── API ──
  saveAction(data) {
    const c = this.cases[this.currentIndex];
    if (!c) return;
    data.loan_id = c.loan_id;
    fetch("/api/deepwork/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    .then(r => r.json())
    .then(res => {
      if (res.error) { this.showToast("Алдаа: " + res.error, true); return; }
      this.showToast(res.message || "Амжилттай!");
      this.nextCard();
    })
    .catch(e => this.showToast("Сүлжээний алдаа", true));
  },

  // ── Navigation ──
  nextCard() {
    this.cases.splice(this.currentIndex, 1);
    this.level = 1;
    this.notes = "";
    if (this.cases.length === 0 || this.currentIndex >= this.cases.length) {
      this.showBatchComplete();
    } else {
      // ANIMATION_HOOK: add .dw-card-exit then .dw-card-enter
      this.renderCard();
    }
  },

  // ── Render Card ──
  renderCard() {
    const ov = document.getElementById("dwOverlay");
    if (!ov) return;
    const c = this.cases[this.currentIndex];
    if (!c) return;

    const total = this.cases.length + this.stats.called + this.stats.sms + this.stats.skipped;
    const done = this.stats.called + this.stats.sms + this.stats.skipped;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    const streak = c.no_answer_streak || 0;
    const broken = c.broken_promise;

    let alerts = "";
    if (streak >= 3) alerts += `<div class="dw-alert dw-alert-orange">⚠️ ${streak} удаа залгасан, хариу өгөөгүй — SMS илгээх үү?</div>`;
    if (broken) alerts += `<div class="dw-alert dw-alert-red">⚠️ Амлалт биелээгүй! Амласан: ${broken}</div>`;
    if (c.days_overdue >= 18 && c.days_overdue <= 22) alerts += `<div class="dw-alert dw-alert-yellow">⏰ ${c.days_overdue} хоног — Удахгүй 21 хоног (салбар уулзалт шаардлагатай)</div>`;
    if (c.days_overdue >= 28 && c.days_overdue <= 32) alerts += `<div class="dw-alert dw-alert-red">🔴 ${c.days_overdue} хоног — Албан мэдэгдэл шаардлагатай</div>`;

    const contacts = (c.recent_contacts || []).map(ct =>
      `<div class="dw-history-item">
        <span class="dw-hist-date">${ct.date}</span>
        <span>${ct.type_icon} ${ct.type_label}</span>
        <span class="dw-hist-result">${ct.was_reached ? "✅ Хүрсэн" : "❌ Хүрээгүй"}</span>
        ${ct.notes ? `<span class="dw-hist-notes">${ct.notes}</span>` : ""}
      </div>`
    ).join("") || `<div class="dw-history-item dw-muted">Холбоо барих бүртгэл алга</div>`;

    const parties = (c.related_parties || []).map(p =>
      `<div class="dw-party">
        <span>${p.relationship}: <strong>${p.name}</strong></span>
        <a href="tel:${p.phone}" class="dw-phone-btn">📞 ${p.phone}</a>
      </div>`
    ).join("") || "";

    const riskColor = c.risk_score >= 75 ? "#DC2626" : c.risk_score >= 50 ? "#EA580C" : c.risk_score >= 25 ? "#CA8A04" : "#16A34A";

    let kbHtml = "";
    if (this.level === 1) {
      kbHtml = `
        <div class="dw-kb-level">Юу болсон бэ?</div>
        <div class="dw-kb-options">
          <div class="dw-kb-key" onclick="DeepWork.action_noAnswer()"><span class="dw-kb-badge">1</span> 📵 Хариугүй</div>
          <div class="dw-kb-key" onclick="DeepWork.level=2;DeepWork.renderCard()"><span class="dw-kb-badge">2</span> 📞 Хариу өгсөн</div>
          <div class="dw-kb-key" onclick="DeepWork.action_wrongNumber()"><span class="dw-kb-badge">3</span> ❌ Утас буруу</div>
          <div class="dw-kb-key" onclick="DeepWork.action_smsSent()"><span class="dw-kb-badge">4</span> 📱 SMS</div>
          <div class="dw-kb-key" onclick="DeepWork.action_skip()"><span class="dw-kb-badge">⎵</span> ⏭️ Алгасах</div>
          <div class="dw-kb-key dw-kb-esc" onclick="DeepWork.exit()"><span class="dw-kb-badge">Esc</span> 🚪 Гарах</div>
        </div>`;
    } else if (this.level === 2) {
      kbHtml = `
        <div class="dw-kb-level">Юу гэсэн бэ? <small>(тэмдэглэл доор бичнэ үү)</small></div>
        <div class="dw-kb-options">
          <div class="dw-kb-key" onclick="DeepWork.level=3;DeepWork.renderCard()"><span class="dw-kb-badge">1</span> ✅ Төлнө гэж амласан</div>
          <div class="dw-kb-key" onclick="DeepWork.action_paid()"><span class="dw-kb-badge">2</span> 💰 Аль хэдийн төлсөн</div>
          <div class="dw-kb-key" onclick="DeepWork.action_infoGiven()"><span class="dw-kb-badge">3</span> 📋 Мэдээлэл өгсөн</div>
          <div class="dw-kb-key" onclick="DeepWork.action_dispute()"><span class="dw-kb-badge">4</span> ⚡ Маргаантай</div>
          <div class="dw-kb-key" onclick="DeepWork.action_other()"><span class="dw-kb-badge">5</span> 📝 Бусад</div>
          <div class="dw-kb-key dw-kb-esc" onclick="DeepWork.level=1;DeepWork.renderCard()"><span class="dw-kb-badge">Esc</span> ← Буцах</div>
        </div>`;
    } else if (this.level === 3) {
      kbHtml = `
        <div class="dw-kb-level">Хэзээ төлөх вэ?</div>
        <div class="dw-kb-options">
          <div class="dw-kb-key" onclick="DeepWork.action_promise(DeepWork.fmtDate(new Date()))"><span class="dw-kb-badge">1</span> Өнөөдөр</div>
          <div class="dw-kb-key" onclick="(function(){var d=new Date();d.setDate(d.getDate()+1);DeepWork.action_promise(DeepWork.fmtDate(d))})()"><span class="dw-kb-badge">2</span> Маргааш</div>
          <div class="dw-kb-key" onclick="(function(){var d=new Date();d.setDate(d.getDate()+(5-d.getDay()+7)%7||7);DeepWork.action_promise(DeepWork.fmtDate(d))})()"><span class="dw-kb-badge">3</span> Энэ долоо хоног</div>
          <div class="dw-kb-key" onclick="(function(){var d=new Date();d.setDate(d.getDate()+7);DeepWork.action_promise(DeepWork.fmtDate(d))})()"><span class="dw-kb-badge">4</span> Дараа долоо хоног</div>
          <div class="dw-kb-key" onclick="(function(){var d=new Date();d.setDate(25);if(d<new Date())d.setMonth(d.getMonth()+1);DeepWork.action_promise(DeepWork.fmtDate(d))})()"><span class="dw-kb-badge">5</span> Цалингийн өдөр (25)</div>
          <div class="dw-kb-key dw-kb-esc" onclick="DeepWork.level=2;DeepWork.renderCard()"><span class="dw-kb-badge">Esc</span> ← Буцах</div>
        </div>`;
    }

    let notesHtml = "";
    if (this.level >= 2) {
      notesHtml = `
        <div class="dw-notes-area">
          <label>📝 Тэмдэглэл (заавал биш)</label>
          <textarea id="dwNotes" class="dw-notes-input" rows="2" placeholder="Нэмэлт тэмдэглэл бичих...">${this.notes}</textarea>
        </div>`;
    }

    ov.innerHTML = `
      <div class="dw-container">
        <div class="dw-topbar">
          <div class="dw-title">🎯 Deep Work Mode</div>
          <div class="dw-stats-bar">
            📞 ${this.stats.called} &nbsp;|&nbsp; ✅ ${this.stats.reached} &nbsp;|&nbsp; 🤝 ${this.stats.promises} &nbsp;|&nbsp; 💰 ${this.stats.paid} &nbsp;|&nbsp; 📱 ${this.stats.sms}
          </div>
          <div class="dw-progress-text">${this.currentIndex + 1}/${this.cases.length}</div>
        </div>
        <div class="dw-progress-bar"><div class="dw-progress-fill" style="width:${pct}%"></div></div>

        ${alerts}

        <div class="dw-card dw-card-enter">
          <div class="dw-risk-banner" style="background:${riskColor}">
            <span class="dw-risk-score">${c.risk_score}</span>
            <span>${c.risk_score >= 75 ? "Маш өндөр эрсдэл" : c.risk_score >= 50 ? "Өндөр эрсдэл" : c.risk_score >= 25 ? "Дунд эрсдэл" : "Бага эрсдэл"}</span>
            <span class="dw-escalation">📊 Алхам ${c.escalation_stage || 0}/15</span>
          </div>

          <div class="dw-card-body">
            <div class="dw-section">
              <h3>👤 ${c.borrower_name}</h3>
              <div class="dw-field"><span class="dw-label">РД:</span> ${c.register_no || "—"}</div>
              <div class="dw-phones">
                <a href="tel:${c.phone_primary}" class="dw-phone-btn dw-phone-primary">📞 ${c.phone_primary || "—"}</a>
                ${c.phone_secondary ? `<a href="tel:${c.phone_secondary}" class="dw-phone-btn">📞 ${c.phone_secondary}</a>` : ""}
              </div>
              <div class="dw-field"><span class="dw-label">📧</span> ${c.email || "—"}</div>
              <div class="dw-field"><span class="dw-label">🏠</span> ${c.address || "—"}</div>
              ${parties ? `<div class="dw-subsection"><h4>👨‍👩‍👦 Холбогдох этгээд</h4>${parties}</div>` : ""}
            </div>

            <div class="dw-section">
              <h3>💰 Зээлийн мэдээлэл</h3>
              <div class="dw-loan-grid">
                <div class="dw-metric"><div class="dw-metric-val">${Number(c.loan_amount||0).toLocaleString()}₮</div><div class="dw-metric-label">Зээлийн дүн</div></div>
                <div class="dw-metric"><div class="dw-metric-val">${Number(c.balance||0).toLocaleString()}₮</div><div class="dw-metric-label">Үлдэгдэл</div></div>
                <div class="dw-metric dw-metric-highlight"><div class="dw-metric-val">${Number(c.overdue_amount||0).toLocaleString()}₮</div><div class="dw-metric-label">Хэтэрсэн дүн</div></div>
                <div class="dw-metric dw-metric-highlight"><div class="dw-metric-val">${c.days_overdue} хоног</div><div class="dw-metric-label">Хэтэрсэн</div></div>
              </div>
              <div class="dw-field"><span class="dw-label">Бүтээгдэхүүн:</span> ${c.product_type || "—"}</div>
              <div class="dw-field"><span class="dw-label">Салбар:</span> ${c.branch || "—"}</div>
              <div class="dw-field"><span class="dw-label">Ангилал:</span> ${c.classification || "—"}</div>
              <div class="dw-field"><span class="dw-label">Зээлийн дугаар:</span> ${c.loan_number || "—"}</div>

              <div class="dw-subsection">
                <h4>🕐 Сүүлийн холбоо барилт</h4>
                ${contacts}
              </div>
            </div>
          </div>

          ${notesHtml}
        </div>

        <div class="dw-keyboard">
          ${kbHtml}
        </div>
      </div>
    `;

    // Save notes on input
    const ta = document.getElementById("dwNotes");
    if (ta) ta.addEventListener("input", () => { DeepWork.notes = ta.value; });
  },

  // ── Batch Complete ──
  showBatchComplete() {
    const ov = document.getElementById("dwOverlay");
    if (!ov) return;
    const s = this.stats;
    const total = s.called + s.sms + s.skipped;
    ov.innerHTML = `
      <div class="dw-container">
        <div class="dw-complete">
          <h2>🎉 Багц дууслаа!</h2>
          <p>${total} хэрэг боловсруулсан</p>
          <div class="dw-final-stats">
            <div class="dw-stat-card"><div class="dw-stat-val">${s.called}</div><div class="dw-stat-label">📞 Залгасан</div></div>
            <div class="dw-stat-card"><div class="dw-stat-val">${s.reached}</div><div class="dw-stat-label">✅ Хүрсэн</div></div>
            <div class="dw-stat-card"><div class="dw-stat-val">${s.promises}</div><div class="dw-stat-label">🤝 Амлалт</div></div>
            <div class="dw-stat-card"><div class="dw-stat-val">${s.paid}</div><div class="dw-stat-label">💰 Төлсөн</div></div>
            <div class="dw-stat-card"><div class="dw-stat-val">${s.sms}</div><div class="dw-stat-label">📱 SMS</div></div>
            <div class="dw-stat-card"><div class="dw-stat-val">${s.skipped}</div><div class="dw-stat-label">⏭️ Алгассан</div></div>
          </div>
          <div class="dw-complete-actions">
            <button class="dw-btn dw-btn-primary" onclick="DeepWork.loadBatch(${this.page + 1})">📋 Дараагийн 10 хэрэг →</button>
            <button class="dw-btn dw-btn-outline" onclick="DeepWork.exit()">🚪 Дашбоард руу буцах</button>
          </div>
        </div>
      </div>
    `;
  },

  showEmpty() {
    this.showOverlay();
    const ov = document.getElementById("dwOverlay");
    ov.innerHTML = `
      <div class="dw-container">
        <div class="dw-complete">
          <h2>✅ Бүгд дууслаа!</h2>
          <p>Залгах хэрэг алга байна</p>
          <button class="dw-btn dw-btn-outline" onclick="DeepWork.exit()">← Дашбоард руу буцах</button>
        </div>
      </div>
    `;
  },

  // ── Toast ──
  showToast(msg, isError) {
    let t = document.getElementById("dwToast");
    if (!t) {
      t = document.createElement("div");
      t.id = "dwToast";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.className = "dw-toast" + (isError ? " dw-toast-error" : "");
    t.style.display = "block";
    setTimeout(() => { t.style.display = "none"; }, 2000);
  },

  // ── Exit ──
  exit() {
    this.isActive = false;
    this.detachKeys();
    this.hideOverlay();
    // Refresh the dashboard
    location.reload();
  },
};
