// ====== DOM 引用 ======
var loginPage = document.getElementById("loginPage");
var uploadPage = document.getElementById("uploadPage");
var usernameInput = document.getElementById("username");
var passwordInput = document.getElementById("password");
var loginError = document.getElementById("loginError");
var btnLogin = document.getElementById("btnLogin");
var btnLogout = document.getElementById("btnLogout");
var kickedOverlay = document.getElementById("kickedOverlay");
var kickedCountdownEl = document.getElementById("kickedCountdown");
var btnKickedOk = document.getElementById("btnKickedOk");

// ====== 会话检查 ======
var kickedCountdownTimer = null;
var kickedCountdownSeconds = 0;

function checkSession() {
  fetch("/check_session", { method: "GET", credentials: "same-origin" })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.code === 0) {
        showUploadPage();
      } else if (data.msg && data.msg.indexOf("踢出") !== -1) {
        kickOut();
      }
    })
    .catch(function () {});
}

checkSession();

// ====== 登录 ======
btnLogin.addEventListener("click", function () {
  var username = usernameInput.value.trim();
  var password = passwordInput.value;
  if (!username || !password) {
    loginError.textContent = "请输入用户名和密码";
    return;
  }

  btnLogin.disabled = true;
  btnLogin.textContent = "登录中...";
  loginError.textContent = "";

  fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username, password: password }),
    credentials: "same-origin"
  })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.code === 0) {
        showUploadPage();
      } else {
        loginError.textContent = data.msg;
      }
    })
    .catch(function (err) {
      loginError.textContent = "网络错误: " + err.message;
    })
    .finally(function () {
      btnLogin.disabled = false;
      btnLogin.textContent = "登 录";
    });
});

passwordInput.addEventListener("keydown", function (e) {
  if (e.key === "Enter") btnLogin.click();
});

// ====== 退出 ======
btnLogout.addEventListener("click", function () {
  fetch("/logout", { method: "POST", credentials: "same-origin" })
    .finally(function () {
      loginPage.style.display = "block";
      uploadPage.style.display = "none";
      clearFile();
    });
});

// ====== 被踢出 ======
function kickOut() {
  stopKickedCountdown();
  uploadPage.style.display = "none";
  loginPage.style.display = "none";
  kickedOverlay.style.display = "flex";

  kickedCountdownSeconds = 60;
  if (kickedCountdownEl) kickedCountdownEl.textContent = kickedCountdownSeconds + " 秒后自动返回登录页";

  kickedCountdownTimer = setInterval(function () {
    kickedCountdownSeconds--;
    if (kickedCountdownEl) kickedCountdownEl.textContent = kickedCountdownSeconds + " 秒后自动返回登录页";
    if (kickedCountdownSeconds <= 0) {
      stopKickedCountdown();
      returnToLogin();
    }
  }, 1000);
}

function stopKickedCountdown() {
  if (kickedCountdownTimer) {
    clearInterval(kickedCountdownTimer);
    kickedCountdownTimer = null;
  }
}

function returnToLogin() {
  stopKickedCountdown();
  kickedOverlay.style.display = "none";
  loginPage.style.display = "block";
  clearFile();
}

btnKickedOk.addEventListener("click", returnToLogin);

function showUploadPage() {
  loginPage.style.display = "none";
  uploadPage.style.display = "block";
  usernameInput.value = "";
  passwordInput.value = "";
  loginError.textContent = "";
}

// ====== 模式切换 ======
var MODE_STOCK = "stock";
var MODE_PREMIUM = "premium";
var MODE_DOWNLOAD = "download";

var UPLOAD_MODES = {
  stock: { label: "更新股票监控表", endpoint: "/update_ah_rate" },
  premium: { label: "更新溢价监控表", endpoint: "/premium_update" }
};

var uploadMode = MODE_STOCK;
var file = null;

var subtitle = document.getElementById("subtitle");
var btnModeStock = document.getElementById("btnModeStock");
var btnModePremium = document.getElementById("btnModePremium");
var btnModeDownload = document.getElementById("btnModeDownload");
var uploadSection = document.getElementById("uploadSection");
var downloadSection = document.getElementById("downloadSection");
var dropZone = document.getElementById("dropZone");
var dropHint = document.getElementById("dropHint");
var fileInfo = document.getElementById("fileInfo");
var fileName = document.getElementById("fileName");
var fileSize = document.getElementById("fileSize");
var fileInput = document.getElementById("fileInput");
var btnUpload = document.getElementById("btnUpload");
var btnClear = document.getElementById("btnClear");
var resultSuccess = document.getElementById("resultSuccess");
var resultError = document.getElementById("resultError");
var resultPath = document.getElementById("resultPath");
var resultSize = document.getElementById("resultSize");
var resultTime = document.getElementById("resultTime");
var errorMsg = document.getElementById("errorMsg");

function switchMode(mode) {
  uploadMode = mode;
  btnModeStock.classList.toggle("active", mode === MODE_STOCK);
  btnModePremium.classList.toggle("active", mode === MODE_PREMIUM);
  btnModeDownload.classList.toggle("active", mode === MODE_DOWNLOAD);

  resultSuccess.classList.remove("show");
  resultError.classList.remove("show");
  clearFile();
  clearDownloadResults();

  if (mode === MODE_DOWNLOAD) {
    uploadSection.style.display = "none";
    downloadSection.style.display = "block";
    subtitle.style.display = "none";
  } else {
    uploadSection.style.display = "block";
    downloadSection.style.display = "none";
    subtitle.style.display = "";
    var cfg = UPLOAD_MODES[mode];
    subtitle.textContent = "";
    btnUpload.textContent = cfg.label;
  }
}

btnModeStock.addEventListener("click", function () { switchMode(MODE_STOCK); });
btnModePremium.addEventListener("click", function () { switchMode(MODE_PREMIUM); });
btnModeDownload.addEventListener("click", function () { switchMode(MODE_DOWNLOAD); });

// ====== 上传逻辑 ======
function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function selectFile(f) {
  file = f;
  dropHint.style.display = "none";
  fileInfo.style.display = "flex";
  fileName.textContent = f.name;
  fileSize.textContent = fmtSize(f.size);
  dropZone.classList.add("has-file");
  btnUpload.disabled = false;
  btnClear.style.display = "inline-block";
  resultSuccess.classList.remove("show");
  resultError.classList.remove("show");
}

function clearFile() {
  file = null;
  dropHint.style.display = "block";
  fileInfo.style.display = "none";
  dropZone.classList.remove("has-file");
  btnUpload.disabled = true;
  btnClear.style.display = "none";
  fileInput.value = "";
  resultSuccess.classList.remove("show");
  resultError.classList.remove("show");
}

dropZone.addEventListener("click", function () { fileInput.click(); });
dropZone.addEventListener("dragover", function (e) {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", function () { dropZone.classList.remove("drag-over"); });
dropZone.addEventListener("drop", function (e) {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  var f = e.dataTransfer.files[0];
  if (f) selectFile(f);
});
fileInput.addEventListener("change", function () {
  var f = fileInput.files[0];
  if (f) selectFile(f);
});
btnClear.addEventListener("click", function (e) {
  e.stopPropagation();
  clearFile();
});
btnUpload.addEventListener("click", function () {
  if (!file) return;
  btnUpload.disabled = true;
  btnUpload.textContent = "上传中...";
  resultSuccess.classList.remove("show");
  resultError.classList.remove("show");

  fetch(UPLOAD_MODES[uploadMode].endpoint, {
    method: "POST", body: file, credentials: "same-origin"
  })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.code === 0) {
        resultPath.textContent = data.data.file;
        resultSize.textContent = fmtSize(data.data.size);
        resultTime.textContent = data.data.modified;
        resultSuccess.classList.add("show");
      } else if (data.code === 401) {
        kickOut();
      } else {
        errorMsg.textContent = data.msg || "上传失败";
        resultError.classList.add("show");
      }
    })
    .catch(function (err) {
      errorMsg.textContent = err.message;
      resultError.classList.add("show");
    })
    .finally(function () {
      btnUpload.disabled = false;
      btnUpload.textContent = UPLOAD_MODES[uploadMode].label;
    });
});

// ====== 下载逻辑 ======
var dlDate = document.getElementById("dlDate");
var dlCode = document.getElementById("dlCode");
var btnSearch = document.getElementById("btnSearch");
var downloadResults = document.getElementById("downloadResults");

function clearDownloadResults() {
  downloadResults.innerHTML = "";
  dlDate.value = "";
  dlCode.value = "";
}

dlDate.addEventListener("keydown", function (e) {
  if (e.key === "Enter") btnSearch.click();
});
dlCode.addEventListener("keydown", function (e) {
  if (e.key === "Enter") btnSearch.click();
});

function isDateRange(val) { return /^\d{8}-\d{8}$/.test(val); }
function isSingleDate(val) { return /^\d{8}$/.test(val); }

btnSearch.addEventListener("click", function () {
  var date = dlDate.value.trim();
  var code = dlCode.value.trim();

  if (!date || !code) {
    downloadResults.innerHTML = '<p class="download-empty">请输入日期和股票代码</p>';
    return;
  }
  if (!isSingleDate(date) && !isDateRange(date)) {
    downloadResults.innerHTML = '<p class="download-empty">日期格式错误，应为 yyyyMMdd 或 yyyyMMdd-yyyyMMdd</p>';
    return;
  }
  if (!/^\d{6}$/.test(code)) {
    downloadResults.innerHTML = '<p class="download-empty">代码格式错误，应为 6 位数字</p>';
    return;
  }

  btnSearch.disabled = true;
  btnSearch.textContent = "处理中...";
  downloadResults.innerHTML = "";

  if (isDateRange(date)) {
    // 日期范围 → 打包下载
    fetch("/search_csv?date=" + date + "&code=" + code, {
      method: "GET", credentials: "same-origin"
    })
      .then(function (res) {
        if (res.status === 401) { kickOut(); return null; }
        if (res.status === 404) {
          res.json().then(function (d) { downloadResults.innerHTML = '<p class="download-empty">' + d.msg + '</p>'; });
          return null;
        }
        if (!res.ok) throw new Error("下载失败");
        return res.blob();
      })
      .then(function (blob) {
        if (!blob) return;
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = code + "_" + date + ".zip";
        a.click();
        URL.revokeObjectURL(url);
        downloadResults.innerHTML = '<p class="download-empty" style="color:#52c41a;">下载成功：' + code + '_' + date + '.zip</p>';
      })
      .catch(function (err) {
        downloadResults.innerHTML = '<p class="download-empty">下载失败: ' + err.message + '</p>';
      })
      .finally(function () {
        btnSearch.disabled = false;
        btnSearch.textContent = "搜索";
      });
  } else {
    // 单日期 → 搜索并列出文件
    fetch("/search_csv?date=" + date + "&code=" + code, {
      method: "GET", credentials: "same-origin"
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.code === 401) { kickOut(); return; }
        if (data.code !== 0) {
          downloadResults.innerHTML = '<p class="download-empty">' + data.msg + '</p>';
          return;
        }
        var files = data.data.files;
        if (!files || files.length === 0) {
          downloadResults.innerHTML = '<p class="download-empty">未找到以 "' + code + '" 开头的 CSV 文件</p>';
          return;
        }
        var dir = data.data.dir;
        var html = '<p class="download-dir">目录: <code>' + dir + '</code></p><ul class="file-list">';
        for (var i = 0; i < files.length; i++) {
          html += '<li class="file-item">';
          html += '<span class="file-item-name">' + files[i] + '</span>';
          html += '<button class="btn btn-download" data-dir="' + encodeURIComponent(dir) +
            '" data-file="' + encodeURIComponent(files[i]) + '">下载</button>';
          html += '</li>';
        }
        html += '</ul>';
        downloadResults.innerHTML = html;

        var btns = downloadResults.querySelectorAll(".btn-download");
        for (var j = 0; j < btns.length; j++) {
          btns[j].addEventListener("click", function () {
            var d = this.getAttribute("data-dir");
            var f = this.getAttribute("data-file");
            fetch("/download_file?dir=" + d + "&file=" + f, { method: "GET", credentials: "same-origin" })
              .then(function (res) {
                if (res.status === 401) { kickOut(); return; }
                if (!res.ok) throw new Error("下载失败");
                return res.blob();
              })
              .then(function (blob) {
                if (!blob) return;
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url;
                a.download = f;
                a.click();
                URL.revokeObjectURL(url);
              });
          });
        }
      })
      .catch(function (err) {
        downloadResults.innerHTML = '<p class="download-empty">网络错误: ' + err.message + '</p>';
      })
      .finally(function () {
        btnSearch.disabled = false;
        btnSearch.textContent = "搜索";
      });
  }
});
