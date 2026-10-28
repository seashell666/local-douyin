/* data-my.js —— "我"页数据源（my 变体）
 * 读取 my_posts.json（50 条个人作品，抖音原始结构），映射成共享引擎需要的字段。
 * 注意：这里只负责"数据来源"，播放功能由 player-engine.js 提供。 */
function createMyDataSource() {
  var _all = null;

  function load() {
    if (_all) return Promise.resolve(_all);
    // cache:no-store + 时间戳双保险：旧版 my_posts.json 是扁平结构（无 author），
    // 一旦被浏览器/WebView 缓存，会导致头像、昵称全部读不到（显示"我"字占位）。
    return fetch("/my_posts.json?cv=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("my_posts http " + r.status);
        return r.json();
      })
      .then(function (rows) {
        _all = (rows || []).map(function (v) {
          var st = v.stats || {};
          var aw = v.author || {};
          return {
            id: v.aweme_id,
            aweme_id: v.aweme_id,
            url: "/api/my/works/" + v.aweme_id + "/stream",
            cover_url: v.cover || "",
            cover: v.cover || "",
            author: aw.nickname || "我",
            title: v.desc || "",
            avatar_url: aw.avatar || "",
            sec_uid: aw.sec_uid || "",
            like_count: st.digg || 0,
            comment_count: st.comment || 0,
            collect_count: st.collect || 0,
            share_count: st.share || 0,
            media_type: "video",
            is_note: false,
            is_following: false,
            duration: (v.duration || 0) / 1000
          };
        });
        return _all;
      });
  }

  return {
    // 引擎统一调用：fetch(offset, limit) → { items, nextOffset, hasMore }
    fetch: function (offset, limit) {
      return load().then(function (all) {
        var start = offset || 0;
        var items = all.slice(start, start + limit);
        return {
          items: items,
          nextOffset: start + items.length,
          hasMore: start + items.length < all.length
        };
      });
    },
    // 供九宫格渲染直接拿全部（不经引擎）
    all: function () { return load(); }
  };
}
