/* init-home.js —— 首页初始化：创建 home 引擎并自动启动 */
(function () {
  var dataSource = createHomeDataSource();
  var engine = window.createPlayerEngine({
    variant: "home",
    rootEl: document.getElementById("stage"),
    sliderEl: document.getElementById("slider"),
    loadingEl: document.getElementById("loading"),
    toastEl: document.getElementById("toast"),
    musicPageEl: document.getElementById("musicPage"),
    dataSource: dataSource,
    autoStart: true,
    showSplash: true
  });
  window.__engine = engine;

  // 支持 ?page=friends / messages（从 my 页 tab 跳回时定位）
  try {
    var p = new URLSearchParams(location.search).get("page");
    if (p === "friends" && window.switchPage) window.switchPage("friends");
    else if (p === "messages" && window.switchPage) window.switchPage("messages");
  } catch (e) {}
})();
