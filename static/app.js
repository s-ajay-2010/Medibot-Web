/* ---------------- CHAT ---------------- */
async function askAI() {
  const input = document.getElementById("chatInput").value.trim();
  const output = document.getElementById("chatOutput");

  if (!input) {
    output.innerText = "Please enter a question.";
    return;
  }

  output.innerText = "Thinking...";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: input })
    });

    const data = await res.json();
    output.innerText = data.reply || "No response.";
  } catch {
    output.innerText = "Server error.";
  }
}

/* ---------------- SUMMARIZE ---------------- */
async function summarize() {
  const text = document.getElementById("summaryInput").value.trim();
  const output = document.getElementById("summaryOutput");

  if (!text) {
    output.innerText = "Paste some medical text first.";
    return;
  }

  output.innerText = "Summarizing...";

  try {
    const res = await fetch("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });

    const data = await res.json();
    output.innerText = data.summary || "No summary returned.";
  } catch {
    output.innerText = "Server error.";
  }
}

/* ---------------- IMAGE ---------------- */
async function uploadImage() {
  const fileInput = document.getElementById("imageFile");
  const output = document.getElementById("imageOutput");

  if (!fileInput.files.length) {
    output.innerText = "Please choose an image.";
    return;
  }

  output.innerText = "Analyzing image...";

  const formData = new FormData();
  formData.append("image", fileInput.files[0]);

  try {
    const res = await fetch("/api/upload_image", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    output.innerText =
      data.medical_assistance ||
      data.error ||
      "No analysis returned.";
  } catch {
    output.innerText = "Image analysis failed.";
  }
}

/* ---------------- REMINDERS ---------------- */
async function addReminder() {
  const name = document.getElementById("reminderName").value.trim();
  const time = document.getElementById("reminderTime").value;
  const status = document.getElementById("reminderStatus");

  if (!name || !time) {
    status.innerText = "Please enter name and time.";
    return;
  }

  status.innerText = "Saving...";

  try {
    const res = await fetch("/api/reminder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, time })
    });

    const data = await res.json();

    if (data.ok) {
      status.innerText = "Reminder added successfully ✅";
      document.getElementById("reminderName").value = "";
      document.getElementById("reminderTime").value = "";
      loadReminders();
    } else {
      status.innerText = "Failed to add reminder.";
    }
  } catch {
    status.innerText = "Server error.";
  }
}

async function loadReminders() {
  const res = await fetch("/api/reminders");
  const data = await res.json();

  const list = document.getElementById("reminderList");
  list.innerHTML = "";

  data.reminders.forEach(r => {
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
}

async function completeReminder(id) {
  await fetch(`/api/reminder/${id}/complete`, { method: "POST" });
}

async function deleteCompletedReminders() {
  await fetch("/api/reminders/completed", { method: "DELETE" });
  loadReminders();
}

/* ---------------- WATER ---------------- */
async function addWater() {
  const res = await fetch("/api/water", { method: "POST" });
  const data = await res.json();
  document.getElementById("waterCount").innerText = data.count;
}

async function loadWater() {
  const res = await fetch("/api/water");
  const data = await res.json();
  document.getElementById("waterCount").innerText = data.count;
}

/* ---------------- DAILY SUMMARY ---------------- */
async function dailySummary() {
  const output = document.getElementById("chatOutput");
  output.innerText = "Generating daily summary...";

  try {
    const res = await fetch("/api/daily_summary");
    const data = await res.json();
    output.innerText = data.summary || "No summary available.";
  } catch {
    output.innerText = "Server error.";
  }
}

/* ---------------- INIT ---------------- */
window.addEventListener("load", () => {
  loadReminders();
  loadWater();
});
