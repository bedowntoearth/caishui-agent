/**
 * 网络请求工具 - 封装 wx.request
 * 统一处理 baseURL、token 注入、错误提示
 */

const BASE_URL = 'http://192.168.1.80:8000/api/v1'; // 本地真机调试

/**
 * 通用请求方法
 * @param {string} url  接口路径（相对路径）
 * @param {string} method  HTTP方法
 * @param {object} data   请求体数据
 * @param {boolean} showLoading  是否显示loading
 */
function request(url, method = 'GET', data = {}, showLoading = true) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('access_token');
    const header = {
      'Content-Type': 'application/json',
    };
    if (token) {
      header['Authorization'] = `Bearer ${token}`;
    }

    if (showLoading) {
      wx.showLoading({ title: '加载中...', mask: true });
    }

    wx.request({
      url: BASE_URL + url,
      method,
      data,
      header,
      success(res) {
        if (showLoading) wx.hideLoading();
        if (res.statusCode === 401) {
          // token过期，跳转登录
          wx.removeStorageSync('access_token');
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error('未登录或登录已过期'));
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          const body = res.data;
          // 兼容多种响应格式：{code: 200, data: {...}} 或 {has_data: true, ...} 或直接返回数据 {content: "..."}
          if (body && (body.code === 200 || body.has_data !== undefined || body.content !== undefined || body.result !== undefined)) {
            resolve(body);
          } else {
            const msg = body.message || '请求失败';
            wx.showToast({ title: msg, icon: 'none', duration: 2000 });
            reject(new Error(msg));
          }
        } else {
          const msg = `服务器错误(${res.statusCode})`;
          wx.showToast({ title: msg, icon: 'none', duration: 2000 });
          reject(new Error(msg));
        }
      },
      fail(err) {
        if (showLoading) wx.hideLoading();
        const msg = err.errMsg || '网络请求失败';
        wx.showToast({ title: '网络异常，请检查连接', icon: 'none', duration: 2000 });
        reject(new Error(msg));
      },
    });
  });
}

/**
 * GET 请求
 */
function get(url, params = {}, showLoading = true) {
  // 将params拼接到url
  const queryStr = Object.keys(params)
    .filter(k => params[k] !== undefined && params[k] !== null && params[k] !== '')
    .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&');
  const fullUrl = queryStr ? `${url}?${queryStr}` : url;
  return request(fullUrl, 'GET', {}, showLoading);
}

/**
 * POST 请求
 */
function post(url, data = {}, showLoading = true) {
  return request(url, 'POST', data, showLoading);
}

/**
 * PUT 请求
 */
function put(url, data = {}, showLoading = true) {
  return request(url, 'PUT', data, showLoading);
}

/**
 * DELETE 请求
 */
function del(url, showLoading = false) {
  return request(url, 'DELETE', {}, showLoading);
}

/**
 * SSE 流式请求（AI评估流式输出）
 * 微信小程序没有原生EventSource，使用请求读取完整响应模拟
 */
function streamRequest(url, data = {}, onChunk, onDone, onError) {
  const token = wx.getStorageSync('access_token');
  const header = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  };
  if (token) header['Authorization'] = `Bearer ${token}`;

  // 微信小程序不支持流式读取，退化为普通POST然后解析SSE格式
  wx.request({
    url: BASE_URL + url,
    method: 'POST',
    data,
    header,
    success(res) {
      if (res.statusCode === 200) {
        // 解析SSE格式 "data: ...\n\n"
        const text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
        const lines = text.split('\n');
        let result = '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const chunk = line.slice(6);
            if (chunk === '[DONE]') continue;
            try {
              const parsed = JSON.parse(chunk);
              if (parsed.content) {
                result += parsed.content;
                if (onChunk) onChunk(parsed.content, result);
              }
            } catch (e) {
              // 纯文本chunk
              result += chunk;
              if (onChunk) onChunk(chunk, result);
            }
          }
        }
        if (onDone) onDone(result);
      } else {
        if (onError) onError(new Error(`HTTP ${res.statusCode}`));
      }
    },
    fail(err) {
      if (onError) onError(err);
    },
  });
}

module.exports = { get, post, put, del, streamRequest, BASE_URL };
