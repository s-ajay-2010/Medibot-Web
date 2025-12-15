async function loadReminders() {
  const res = await fetch("/api/reminders");
  const data = await res.json();

  const list = document.getElementById("reminderList");
  const deleteBtn = document.getElementById("deleteBtn");

  list.innerHTML = "";

  let hasAny = data.reminders.length > 0;
  let hasCompleted = false;

  data.reminders.forEach(r => {
    if (r.completed) hasCompleted = true;

    const div = document.createElement("div");
    div.className = "check-item";

    div.innerHTML = `
      <label>
        <input type="checkbox"
          ${r.completed ? "checked" : ""}
          onchange="completeReminder(${r.id})">
        <strong>${r.time}</strong> — ${r.name}
      </label>
    `;

    list.appendChild(div);
  });

  // 🔥 BUTTON STATE LOGIC
  if (!hasAny || !hasCompleted) {
    deleteBtn.disabled = true;
    deleteBtn.classList.add("disabled");
  } else {
    deleteBtn.disabled = false;
    deleteBtn.classList.remove("disabled");
  }
}


async function addReminder() {
  const nameInput = document.getElementById("reminderName");
  const timeInput = document.getElementById("reminderTime");

  if (!nameInput.value || !timeInput.value) {
    alert("Enter task and time");
    return;
  }

  await fetch("/api/reminder", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      name: nameInput.value,
      time: timeInput.value
    })
  });

  nameInput.value = "";
  timeInput.value = "";

  loadReminders();
}


async function completeReminder(id) {
  await fetch(`/api/reminder/${id}/complete`, { method: "POST" });
  loadReminders();
}

async function deleteCompletedReminders() {
  await fetch("/api/reminders/completed", { method: "DELETE" });
  loadReminders();
}

/* ---------------- WATER ---------------- */
async function loadWater() {
  const r = await fetch("/api/water");
  const d = await r.json();
  waterCount.innerText = d.count;
}

async function addWater() {
  const r = await fetch("/api/water", { method: "POST" });
  const d = await r.json();
  waterCount.innerText = d.count;
}

/* ---------------- CHAT ---------------- */
async function askAI() {
  chatOutput.innerText = "Thinking...";
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ message: chatInput.value })
  });
  const d = await r.json();
  chatOutput.innerText = d.reply;
}

async function dailySummary() {
  chatOutput.innerText = "Generating...";
  const r = await fetch("/api/daily_summary");
  const d = await r.json();
  chatOutput.innerText = d.summary;
}

/* ---------------- IMAGE ---------------- */
async function uploadImage() {
  const f = new FormData();
  f.append("image", imageFile.files[0]);

  imageOutput.innerText = "Analyzing...";
  const r = await fetch("/api/upload_image", { method: "POST", body: f });
  const d = await r.json();
  imageOutput.innerText = d.medical_assistance;
}

/* ---------------- INIT ---------------- */
window.onload = () => {
  loadReminders();
  loadWater();
};

async function summarize() {
  const text = summaryInput.value.trim();

  if (!text) {
    summaryOutput.innerText = "Enter text to summarize.";
    return;
  }

  summaryOutput.innerText = "Summarizing...";

  try {
    const r = await fetch("/api/summarize", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text })
    });

    const d = await r.json();
    summaryOutput.innerText = d.summary || "No summary returned.";
  } catch {
    summaryOutput.innerText = "Summarize failed (server error).";
  }
}
