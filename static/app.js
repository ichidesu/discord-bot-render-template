const form = document.querySelector("#config-form");
const notice = document.querySelector("#notice");
const saveButton = document.querySelector("#save-button");
const commandsList = document.querySelector("#commands-list");
const repliesList = document.querySelector("#replies-list");

function showNotice(message, type = "success") {
  notice.textContent = message;
  notice.className = `notice visible ${type}`;
  window.clearTimeout(showNotice.timeout);
  showNotice.timeout = window.setTimeout(() => {
    notice.className = "notice";
  }, 4200);
}

function addCommand(command = { name: "", response: "" }) {
  const fragment = document.querySelector("#command-template").content.cloneNode(true);
  const row = fragment.querySelector(".builder-row");
  row.querySelector(".command-name").value = command.name;
  row.querySelector(".command-response").value = command.response;
  row.querySelector(".remove-button").addEventListener("click", () => row.remove());
  commandsList.append(row);
  updatePrefixExamples();
}

function addReply(reply = { trigger: "", response: "", match: "contains" }) {
  const fragment = document.querySelector("#reply-template").content.cloneNode(true);
  const row = fragment.querySelector(".builder-row");
  row.querySelector(".reply-trigger").value = reply.trigger;
  row.querySelector(".reply-response").value = reply.response;
  row.querySelector(".reply-match").value = reply.match;
  row.querySelector(".remove-button").addEventListener("click", () => row.remove());
  repliesList.append(row);
}

function updatePreview() {
  const name = document.querySelector("#bot-name").value || "Bot";
  document.querySelector("#preview-name").textContent = name;
  document.querySelector("#preview-avatar").textContent = name.charAt(0).toUpperCase();
  document.querySelector("#preview-activity").textContent =
    document.querySelector("#activity").value || "アクティビティ未設定";
}

function updatePrefixExamples() {
  const prefix = document.querySelector("#prefix").value || "!";
  document.querySelector("#prefix-example").textContent = prefix;
  document.querySelectorAll(".input-prefix span").forEach((element) => {
    element.textContent = prefix;
  });
}

function populateForm(config) {
  document.querySelector("#bot-name").value = config.bot_name;
  document.querySelector("#prefix").value = config.prefix;
  document.querySelector("#activity").value = config.activity;
  document.querySelector("#status").value = config.status;
  document.querySelector("#welcome-enabled").checked = config.welcome.enabled;
  document.querySelector("#welcome-channel").value = config.welcome.channel_id;
  document.querySelector("#welcome-message").value = config.welcome.message;
  document.querySelector("#goodbye-enabled").checked = config.goodbye.enabled;
  document.querySelector("#goodbye-channel").value = config.goodbye.channel_id;
  document.querySelector("#goodbye-message").value = config.goodbye.message;
  document.querySelector("#moderation-enabled").checked = config.moderation.enabled;
  document.querySelector("#blocked-words").value = config.moderation.blocked_words.join("\n");
  document.querySelector("#moderation-warning").value = config.moderation.warning;

  commandsList.replaceChildren();
  repliesList.replaceChildren();
  config.custom_commands.forEach(addCommand);
  config.auto_replies.forEach(addReply);
  updatePreview();
  updatePrefixExamples();
}

function collectConfig() {
  return {
    bot_name: document.querySelector("#bot-name").value,
    prefix: document.querySelector("#prefix").value,
    activity: document.querySelector("#activity").value,
    status: document.querySelector("#status").value,
    welcome: {
      enabled: document.querySelector("#welcome-enabled").checked,
      channel_id: document.querySelector("#welcome-channel").value,
      message: document.querySelector("#welcome-message").value,
    },
    goodbye: {
      enabled: document.querySelector("#goodbye-enabled").checked,
      channel_id: document.querySelector("#goodbye-channel").value,
      message: document.querySelector("#goodbye-message").value,
    },
    moderation: {
      enabled: document.querySelector("#moderation-enabled").checked,
      blocked_words: document
        .querySelector("#blocked-words")
        .value.split("\n")
        .map((word) => word.trim())
        .filter(Boolean),
      warning: document.querySelector("#moderation-warning").value,
    },
    custom_commands: [...commandsList.querySelectorAll(".builder-row")].map((row) => ({
      name: row.querySelector(".command-name").value,
      response: row.querySelector(".command-response").value,
    })),
    auto_replies: [...repliesList.querySelectorAll(".builder-row")].map((row) => ({
      trigger: row.querySelector(".reply-trigger").value,
      response: row.querySelector(".reply-response").value,
      match: row.querySelector(".reply-match").value,
    })),
  };
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("設定を読み込めませんでした。");
    populateForm(await response.json());
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    const statusLabel = document.querySelector("#sidebar-status");
    const statusDot = document.querySelector("#sidebar-status-dot");
    const guildCount = document.querySelector("#guild-count");
    statusLabel.textContent = status.bot_connected ? "Bot オンライン" : "Bot オフライン";
    guildCount.textContent = status.bot_connected
      ? `${status.guild_count} サーバーに接続中`
      : "トークンまたは接続を確認";
    statusDot.classList.toggle("offline", !status.bot_connected);
  } catch {
    document.querySelector("#sidebar-status").textContent = "状態を取得できません";
  }
}

async function saveConfig() {
  if (!form.reportValidity()) return;
  saveButton.disabled = true;
  saveButton.querySelector("span").textContent = "保存中…";
  try {
    const response = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectConfig()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "保存できませんでした。");
    populateForm(result);
    showNotice("設定を保存しました。Botへすぐに反映されます。");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    saveButton.disabled = false;
    saveButton.querySelector("span").textContent = "変更を保存";
  }
}

document.querySelector("#add-command").addEventListener("click", () => addCommand());
document.querySelector("#add-reply").addEventListener("click", () => addReply());
document.querySelector("#bot-name").addEventListener("input", updatePreview);
document.querySelector("#activity").addEventListener("input", updatePreview);
document.querySelector("#prefix").addEventListener("input", updatePrefixExamples);
saveButton.addEventListener("click", saveConfig);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveConfig();
  }
});

loadConfig();
loadStatus();
window.setInterval(loadStatus, 30000);
