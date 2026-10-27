/* data-home.js —— 首页数据源（home 变体）
 * 走 /api/videos；默认 customer1（后端客户排序：加权随机+3视频夹1音频/图集），
 * URL 带 ?mode=normal 回原测试排序（图集/音频置前交替，每4条夹1视频）。
 * 这里只负责"数据来源 + 排序"，播放功能由 player-engine.js 提供。 */
function createHomeDataSource() {
  var feedMode = "customer1";
  try { feedMode = new URLSearchParams(location.search).get("mode") || "customer1"; }
  catch (e) { feedMode = "customer1"; }

  // 测试排序：图集/音频为主置前且交替，每4条夹1条视频
  function sortNormal(items) {
    var rank = { album: 0, audio: 1, video: 2 };
    var grouped = [[], [], []];
    for (var i = 0; i < items.length; i++) {
      var mt = items[i].media_type || "video";
      grouped[(rank[mt] !== undefined ? rank[mt] : 2)].push(items[i]);
    }
    var pri = [];
    var mi = 0, ai = 0;
    while (mi < grouped[0].length || ai < grouped[1].length) {
      if (mi < grouped[0].length) pri.push(grouped[0][mi++]);
      if (ai < grouped[1].length) pri.push(grouped[1][ai++]);
    }
    var vids = grouped[2];
    var merged = [];
    var vi = 0;
    for (var pi = 0; pi < pri.length; pi++) {
      merged.push(pri[pi]);
      if ((pi + 1) % 4 === 0 && vi < vids.length) { merged.push(vids[vi++]); }
    }
    while (vi < vids.length) { merged.push(vids[vi++]); }
    return merged;
  }

  return {
    fetch: function (offset, limit) {
      var modeParam = feedMode === "customer1" ? "&mode=customer1" : "";
      return fetch("/api/videos?offset=" + offset + "&limit=" + limit + modeParam)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var items = (data.items || []).slice();
          if (feedMode !== "customer1") {
            items = sortNormal(items);
          }
          // customer1 后端已排序；normal 前端排序。offset 沿用后端返回值。
          return {
            items: items,
            nextOffset: data.offset + (data.items ? data.items.length : 0),
            hasMore: data.has_more
          };
        });
    }
  };
}
