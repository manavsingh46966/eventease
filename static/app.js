/**
 * EventEase Frontend Application Logic
 * Modern Mobile-first UI with real-time API binding, load balancing indicator,
 * bottom-sheet modals, category filters, and admin controls.
 */

const $ = (id) => document.getElementById(id);

let allEvents = [];
let currentCategory = "all";
let activeEvent = null;
let adminKey = localStorage.getItem("eventease_admin_key") || "";
let currentRollNo = localStorage.getItem("eventease_roll_no") || "CS24B012";

// Initialize student badge and admin key
document.addEventListener("DOMContentLoaded", () => {
  if ($("studentIdDisplay")) {
    $("studentIdDisplay").textContent = currentRollNo;
  }
  if ($("adminKey") && adminKey) {
    $("adminKey").value = adminKey;
  }
  updateMySeatsBadge();
  loadEvents();
  loadServer();

  // Backdrop click listeners
  $("booking-sheet-backdrop").addEventListener("click", (e) => {
    if (e.target === $("booking-sheet-backdrop")) closeRegistrationModal();
  });
  $("tickets-sheet-backdrop").addEventListener("click", (e) => {
    if (e.target === $("tickets-sheet-backdrop")) closeMySeatsModal();
  });
});

/* ---------- Notifications & Toasts ---------- */
function showNotice(message, isError = false) {
  const banner = $("noticeBanner");
  const text = $("noticeText");
  const icon = $("noticeIcon");
  if (!banner || !text) return;

  text.textContent = message;
  if (isError) {
    banner.className = "mx-3 mt-3 px-4 py-3 rounded-xl text-xs font-medium border shadow-sm transition-all bg-rose-50 border-rose-200 text-rose-800";
    icon.className = "fa-solid fa-triangle-exclamation mt-0.5 text-sm text-rose-600";
  } else {
    banner.className = "mx-3 mt-3 px-4 py-3 rounded-xl text-xs font-medium border shadow-sm transition-all bg-emerald-50 border-emerald-200 text-brand-900";
    icon.className = "fa-solid fa-circle-check mt-0.5 text-sm text-emerald-600";
  }
  banner.classList.remove("hidden");
  banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideNotice() {
  const banner = $("noticeBanner");
  if (banner) banner.classList.add("hidden");
}

/* ---------- API Helper ---------- */
function parseError(data, status) {
  if (status === 429) {
    return "Rate limit reached. Too many requests. Please wait a moment and try again.";
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => (d.msg || "").replace(/^Value error, /, "")).join(". ");
  }
  return data.detail || "An unexpected error occurred.";
}

async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (url.startsWith("/api/admin")) headers["X-Admin-Key"] = adminKey;

  const res = await fetch(url, { ...options, headers });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    /* empty response */
  }

  if (!res.ok) {
    throw new Error(parseError(data, res.status));
  }
  return data;
}

/* ---------- Date Formatting ---------- */
function formatDate(iso) {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch (_) {
    return iso;
  }
}

function generateCode(title, id) {
  const words = title.replace(/[^A-Za-z0-9 ]/g, "").split(" ");
  const prefix = words.map((w) => w[0] || "").join("").slice(0, 3).toUpperCase();
  return `${prefix || "EVT"}-${2026 + id}`;
}

/* ---------- Server & Load Balancer Info ---------- */
async function loadServer() {
  try {
    const data = await api("/api/info");
    const raw = data.served_by || "local / instance";
    const parts = raw.split("/");
    const cluster = parts[0].trim();
    const host = parts[1] ? parts[1].trim() : "NODE";

    if ($("cluster-name")) {
      $("cluster-name").textContent = cluster.includes(".") ? cluster : `${cluster}.cluster-us`;
    }
    if ($("host-name")) {
      $("host-name").textContent = `HOST: ${host}`;
    }
  } catch (_) {
    if ($("cluster-name")) $("cluster-name").textContent = "app.cluster-us";
    if ($("host-name")) $("host-name").textContent = "HOST: STANDALONE";
  }
}

/* ---------- Category Badges Mapping ---------- */
function getCategoryInfo(ev) {
  const text = (ev.title + " " + (ev.description || "")).toLowerCase();
  if (text.includes("hackathon")) {
    return {
      cat: "24h Hackathon",
      catClass: "bg-emerald-50 text-emerald-700 border-emerald-200/60",
      tag: '<i class="fa-solid fa-trophy mr-1 text-[9px]"></i>Prizes Included',
      tagClass: "bg-amber-50 text-amber-600",
      filterGroup: "hackathon"
    };
  }
  if (text.includes("workshop") || text.includes("security") || text.includes("devsecops")) {
    return {
      cat: "Workshop",
      catClass: "bg-blue-50 text-blue-700 border-blue-200/60",
      tag: '<i class="fa-solid fa-laptop-code mr-1 text-[9px]"></i>Hands-on',
      tagClass: "bg-purple-50 text-purple-700",
      filterGroup: "workshop"
    };
  }
  if (text.includes("summit") || text.includes("ai") || text.includes("llm") || text.includes("agent")) {
    return {
      cat: "Summit & Keynote",
      catClass: "bg-purple-50 text-purple-700 border-purple-200/60",
      tag: '<i class="fa-solid fa-microchip mr-1 text-[9px]"></i>GenAI',
      tagClass: "bg-emerald-50 text-emerald-800",
      filterGroup: "summit"
    };
  }
  return {
    cat: "Campus Session",
    catClass: "bg-slate-100 text-slate-700 border-slate-200",
    tag: '<i class="fa-solid fa-award mr-1 text-[9px]"></i>Official',
    tagClass: "bg-slate-100 text-slate-600",
    filterGroup: "all"
  };
}

/* ---------- Render Events Card ---------- */
function buildEventCard(ev) {
  const catInfo = getCategoryInfo(ev);
  const percent = ev.total_seats > 0 ? Math.round((ev.seats_left / ev.total_seats) * 100) : 0;
  const isAvailable = ev.seats_left > 0;
  const isLow = isAvailable && (ev.seats_left / ev.total_seats) <= 0.2;
  const code = generateCode(ev.title, ev.id);

  const card = document.createElement("article");
  card.className = "bg-white rounded-2xl p-5 shadow-card border border-slate-200/90 transition-all hover:border-emerald-300 hover:shadow-lg relative overflow-hidden flex flex-col justify-between";
  card.setAttribute("data-purpose", "event-card");

  card.innerHTML = `
    <div class="absolute top-0 right-0 w-24 h-24 bg-emerald-50 rounded-bl-full pointer-events-none -mr-4 -mt-4 opacity-70"></div>
    
    <div>
      <!-- Header & Category Badge -->
      <div class="flex items-start justify-between gap-2 relative">
        <div>
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-md border ${catInfo.catClass}">
              ${catInfo.cat}
            </span>
            <span class="text-[10px] font-medium px-1.5 py-0.5 rounded ${catInfo.tagClass}">
              ${catInfo.tag}
            </span>
          </div>
          <h4 class="text-base font-bold text-slate-900 leading-tight">${escapeHtml(ev.title)}</h4>
        </div>
        <!-- Capacity Badge -->
        <div class="text-right shrink-0 bg-slate-50 border border-slate-200/80 rounded-xl px-2.5 py-1.5">
          <span class="block text-xl font-black text-brand-800 leading-none">${ev.seats_left}</span>
          <span class="text-[9px] font-medium text-slate-500 uppercase tracking-tighter">of ${ev.total_seats} seats left</span>
        </div>
      </div>

      <!-- Meta Details (Date & Venue) -->
      <div class="mt-3 space-y-1.5 text-xs text-slate-600">
        <div class="flex items-center gap-2 text-slate-700">
          <i class="fa-regular fa-calendar text-emerald-600 w-4 text-center"></i>
          <span class="font-medium">${formatDate(ev.date)}</span>
        </div>
        <div class="flex items-center gap-2 text-slate-600">
          <i class="fa-solid fa-location-dot text-emerald-600 w-4 text-center"></i>
          <span>${escapeHtml(ev.venue)}</span>
        </div>
      </div>

      <!-- Description -->
      ${ev.description ? `
        <p class="mt-3 text-xs text-slate-600 leading-relaxed bg-slate-50/70 p-2.5 rounded-xl border border-slate-100">
          ${escapeHtml(ev.description)}
        </p>
      ` : ""}
    </div>

    <div>

    <!-- Capacity Meter Progress -->
    <div class="mt-3">
      <div class="flex justify-between text-[11px] font-medium text-slate-500 mb-1">
        ${isAvailable ? `
          <span class="text-emerald-700 font-semibold flex items-center gap-1">
            <i class="fa-solid fa-circle-check text-[10px]"></i> Registration Open
          </span>
          <span>${percent}% Availability</span>
        ` : `
          <span class="text-rose-600 font-semibold flex items-center gap-1">
            <i class="fa-solid fa-circle-xmark text-[10px]"></i> Event Full
          </span>
          <span>0 Seats Available</span>
        `}
      </div>
      <div class="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
        <div class="${isAvailable ? (isLow ? 'bg-amber-500' : 'bg-emerald-500') : 'bg-rose-500'} h-1.5 rounded-full" style="width: ${percent}%;"></div>
      </div>
    </div>

    <!-- Register Button Action -->
    <div class="mt-3.5 pt-2 border-t border-slate-100 flex items-center justify-between">
      <span class="text-[11px] text-slate-400 font-mono">CODE: ${code}</span>
      ${isAvailable ? `
        <button type="button" class="reg-btn press-down inline-flex items-center justify-center gap-2 bg-brand-800 hover:bg-brand-900 active:bg-brand-950 text-white font-medium text-xs px-4 py-2.5 rounded-xl shadow-sm transition">
          <span>Register</span>
          <i class="fa-solid fa-arrow-right text-[10px]"></i>
        </button>
      ` : `
        <button type="button" disabled class="inline-flex items-center justify-center gap-2 bg-slate-200 text-slate-500 font-medium text-xs px-4 py-2.5 rounded-xl cursor-not-allowed">
          <span>Event Full</span>
        </button>
      `}
      </div>
    </div>
  `;

  const regBtn = card.querySelector(".reg-btn");
  if (regBtn) {
    regBtn.addEventListener("click", () => openRegistrationModal(ev));
  }

  return card;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/* ---------- Load & Render Events ---------- */
async function loadEvents() {
  try {
    allEvents = await api("/api/events");
    renderFilteredEvents();

    if ($("allCountBadge")) {
      $("allCountBadge").textContent = allEvents.length;
    }

    // Populate admin dropdown
    const select = $("eventSelect");
    if (select) {
      const prevVal = select.value;
      select.innerHTML = "";
      allEvents.forEach((e) => {
        const opt = document.createElement("option");
        opt.value = e.id;
        opt.textContent = `${e.title} (${e.date})`;
        select.appendChild(opt);
      });
      if (prevVal) select.value = prevVal;
    }
  } catch (err) {
    showNotice(err.message, true);
  }
}

function renderFilteredEvents() {
  const container = $("events");
  if (!container) return;
  container.innerHTML = "";

  const filtered = allEvents.filter((ev) => {
    if (currentCategory === "all") return true;
    const cat = getCategoryInfo(ev).filterGroup;
    return cat === currentCategory;
  });

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "text-center py-10 bg-white rounded-2xl border border-slate-200 p-6";
    empty.innerHTML = `
      <div class="w-10 h-10 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-2">
        <i class="fa-regular fa-calendar-xmark"></i>
      </div>
      <p class="text-xs font-semibold text-slate-700">No events found in this category.</p>
      <p class="text-[11px] text-slate-400 mt-1">Organizers can add one under Organizer Tools.</p>
    `;
    container.appendChild(empty);
    return;
  }

  filtered.forEach((ev) => {
    container.appendChild(buildEventCard(ev));
  });
}

function setCategoryFilter(category) {
  currentCategory = category;
  const chips = [
    { id: "chipAll", cat: "all" },
    { id: "chipHackathons", cat: "hackathon" },
    { id: "chipWorkshops", cat: "workshop" },
    { id: "chipSummits", cat: "summit" },
  ];

  chips.forEach((c) => {
    const btn = $(c.id);
    if (!btn) return;
    if (c.cat === category) {
      btn.className = "bg-brand-800 text-white px-3.5 py-1.5 rounded-full shrink-0 shadow-xs flex items-center gap-1.5 press-down transition";
    } else {
      btn.className = "bg-white border border-slate-200 text-slate-700 px-3.5 py-1.5 rounded-full shrink-0 hover:bg-slate-50 transition press-down";
    }
  });

  renderFilteredEvents();
}

/* ---------- Registration Modal (Bottom Sheet) ---------- */
function openRegistrationModal(ev) {
  activeEvent = ev;
  $("modal-event-title").textContent = ev.title;
  $("modal-event-seats").textContent = `${ev.seats_left} seats available`;
  $("regForm").reset();

  // Pre-fill roll number and name
  $("roll-number-input").value = currentRollNo;
  const storedName = localStorage.getItem("eventease_student_name") || "";
  if (storedName) $("regName").value = storedName;

  const msg = $("dlgMsg");
  msg.className = "hidden";
  msg.textContent = "";

  const backdrop = $("booking-sheet-backdrop");
  const sheet = $("booking-sheet");
  backdrop.classList.remove("hidden");
  setTimeout(() => {
    sheet.classList.remove("translate-y-full");
  }, 10);
}

function closeRegistrationModal() {
  const backdrop = $("booking-sheet-backdrop");
  const sheet = $("booking-sheet");
  sheet.classList.add("translate-y-full");
  setTimeout(() => {
    backdrop.classList.add("hidden");
  }, 250);
}

$("regForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!activeEvent) return;

  const confirmBtn = $("confirm");
  const msg = $("dlgMsg");
  const f = new FormData(e.target);
  const name = f.get("name").trim();
  const roll_no = f.get("roll_no").trim().toUpperCase();

  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Holding Seat…</span>';

  try {
    const res = await api(`/api/events/${activeEvent.id}/register`, {
      method: "POST",
      body: JSON.stringify({ name, roll_no }),
    });

    // Store in localStorage
    localStorage.setItem("eventease_roll_no", roll_no);
    localStorage.setItem("eventease_student_name", name);
    currentRollNo = roll_no;
    if ($("studentIdDisplay")) $("studentIdDisplay").textContent = roll_no;

    saveConfirmedTicket({
      eventId: activeEvent.id,
      title: activeEvent.title,
      date: activeEvent.date,
      venue: activeEvent.venue,
      roll_no: roll_no,
      name: name,
      bookedAt: new Date().toISOString(),
    });

    closeRegistrationModal();
    showNotice(`Seat held successfully for "${activeEvent.title}"! Seats remaining: ${res.seats_left}.`, false);
    loadEvents();
    loadServer();
  } catch (err) {
    msg.className = "p-2.5 rounded-xl text-xs font-medium border bg-rose-50 border-rose-200 text-rose-800";
    msg.textContent = err.message;
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="fa-solid fa-ticket"></i><span>Confirm &amp; Hold Seat</span>';
  }
});

/* ---------- My Seats (Confirmed Tickets) ---------- */
function getTickets() {
  try {
    return JSON.parse(localStorage.getItem("eventease_tickets") || "[]");
  } catch (_) {
    return [];
  }
}

function saveConfirmedTicket(ticket) {
  const tickets = getTickets().filter((t) => !(t.eventId === ticket.eventId && t.roll_no === ticket.roll_no));
  tickets.unshift(ticket);
  localStorage.setItem("eventease_tickets", JSON.stringify(tickets));
  updateMySeatsBadge();
}

function updateMySeatsBadge() {
  const count = getTickets().length;
  const badge = $("mySeatsBadge");
  if (badge) {
    if (count > 0) badge.classList.remove("hidden");
    else badge.classList.add("hidden");
  }
}

function openMySeatsModal() {
  const tickets = getTickets();
  const container = $("ticketsContainer");
  container.innerHTML = "";

  if (!tickets.length) {
    container.innerHTML = `
      <div class="text-center py-8 text-slate-400">
        <i class="fa-solid fa-ticket-simple text-3xl mb-2 text-slate-300"></i>
        <p class="text-xs font-semibold text-slate-600">No confirmed tickets yet.</p>
        <p class="text-[11px] text-slate-400 mt-0.5">Register for any campus event to see your held seat here.</p>
      </div>
    `;
  } else {
    tickets.forEach((t) => {
      const item = document.createElement("div");
      item.className = "bg-slate-50 border border-slate-200 rounded-xl p-3 relative overflow-hidden";
      item.innerHTML = `
        <div class="flex items-start justify-between">
          <div>
            <span class="text-[10px] font-bold text-emerald-700 uppercase bg-emerald-100/60 px-1.5 py-0.2 rounded">Confirmed Ticket</span>
            <h4 class="text-xs font-bold text-slate-900 mt-1">${escapeHtml(t.title)}</h4>
            <p class="text-[11px] text-slate-600 mt-0.5"><i class="fa-regular fa-calendar text-emerald-600 mr-1"></i>${formatDate(t.date)} at ${escapeHtml(t.venue)}</p>
          </div>
          <span class="text-xs font-mono font-bold text-brand-900 bg-white border border-slate-200 px-2 py-1 rounded-lg">${escapeHtml(t.roll_no)}</span>
        </div>
      `;
      container.appendChild(item);
    });
  }

  const backdrop = $("tickets-sheet-backdrop");
  const sheet = $("tickets-sheet");
  backdrop.classList.remove("hidden");
  setTimeout(() => {
    sheet.classList.remove("translate-y-full");
  }, 10);
}

function closeMySeatsModal() {
  const backdrop = $("tickets-sheet-backdrop");
  const sheet = $("tickets-sheet");
  sheet.classList.add("translate-y-full");
  setTimeout(() => {
    backdrop.classList.add("hidden");
  }, 250);
}

/* ---------- Student ID Quick Change ---------- */
$("studentBadge").addEventListener("click", () => {
  const newRoll = prompt("Enter Student Roll Number:", currentRollNo);
  if (newRoll && newRoll.trim()) {
    currentRollNo = newRoll.trim().toUpperCase();
    localStorage.setItem("eventease_roll_no", currentRollNo);
    $("studentIdDisplay").textContent = currentRollNo;
    showNotice(`Active roll number set to ${currentRollNo}`, false);
  }
});

/* ---------- Organizer Tools (Admin) ---------- */
function togglePasswordVisibility(fieldId) {
  const input = $(fieldId);
  const icon = $("adminKeyEye");
  if (!input) return;

  if (input.type === "password") {
    input.type = "text";
    if (icon) icon.className = "fa-regular fa-eye-slash";
  } else {
    input.type = "password";
    if (icon) icon.className = "fa-regular fa-eye";
  }
}

$("adminKey").addEventListener("input", (e) => {
  adminKey = e.target.value.trim();
  localStorage.setItem("eventease_admin_key", adminKey);
});

$("eventForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const btn = $("createEventBtn");
  btn.disabled = true;

  try {
    const payload = {
      title: f.get("title").trim(),
      description: (f.get("description") || "").trim(),
      date: f.get("date"),
      venue: f.get("venue").trim(),
      total_seats: Number(f.get("total_seats")),
    };

    const newEv = await api("/api/admin/events", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    e.target.reset();
    showNotice(`Event "${newEv.title}" created successfully!`, false);
    loadEvents();
  } catch (err) {
    showNotice(err.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("loadRegs").addEventListener("click", async () => {
  const id = $("eventSelect").value;
  if (!id) {
    showNotice("Please select an event from the list.", true);
    return;
  }

  const tableWrapper = $("regTableWrapper");
  const tbody = $("regTable").querySelector("tbody");
  tbody.innerHTML = "";

  try {
    const rows = await api(`/api/admin/events/${id}/registrations`);
    if (!rows.length) {
      showNotice("No registrations found for this event yet.", false);
      tableWrapper.classList.add("hidden");
      return;
    }

    rows.forEach((r) => {
      const tr = document.createElement("tr");
      const timeStr = r.registered_at ? new Date(r.registered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "-";
      tr.innerHTML = `
        <td class="font-medium text-slate-800">${escapeHtml(r.name)}</td>
        <td class="font-mono text-emerald-800 font-semibold">${escapeHtml(r.roll_no)}</td>
        <td class="text-slate-500">${timeStr}</td>
      `;
      tbody.appendChild(tr);
    });

    tableWrapper.classList.remove("hidden");
    showNotice(`Showing ${rows.length} attendee registration(s).`, false);
  } catch (err) {
    showNotice(err.message, true);
    tableWrapper.classList.add("hidden");
  }
});

$("deleteEvent").addEventListener("click", async () => {
  const id = $("eventSelect").value;
  if (!id) return;
  if (!confirm("Are you sure you want to permanently delete this event and its registrations?")) {
    return;
  }

  try {
    await api(`/api/admin/events/${id}`, { method: "DELETE" });
    $("regTableWrapper").classList.add("hidden");
    showNotice("Event successfully deleted.", false);
    loadEvents();
  } catch (err) {
    showNotice(err.message, true);
  }
});
