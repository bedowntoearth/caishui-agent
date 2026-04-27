// pages/ai-eval/ai-eval.js
const { get } = require('../../utils/request');
const { getRiskLevelInfo } = require('../../utils/util');

Page({
  data: {
    indicatorId: null,
    indicatorName: '',
    level: '',
    levelText: '',
    levelCls: '',
    reason: '',
    evalContent: '',       // 当前显示的内容（打字机效果用）
    fullContent: '',       // 完整内容
    generating: false,
    hasError: false,
    errorMsg: '',
    riskIndex: null,
    typingIndex: 0,        // 当前打字位置
  },

  onLoad(options) {
    const { indicatorId, indicatorName, level, reason, riskIndex } = options;
    const levelInfo = getRiskLevelInfo(level);
    this.setData({
      indicatorId: indicatorId ? parseInt(indicatorId) : null,
      indicatorName: indicatorName ? decodeURIComponent(indicatorName) : '',
      level: level || 'warning',
      levelText: levelInfo.text,
      levelCls: levelInfo.cls,
      reason: reason ? decodeURIComponent(reason) : '',
      riskIndex: riskIndex ? parseInt(riskIndex) : null,
    });

    // 页面加载后自动触发AI评估
    this.loadEval();
  },

  onUnload() {
    // 页面卸载时停止打字机效果
    if (this.typingTimer) {
      clearTimeout(this.typingTimer);
    }
  },

  onShareAppMessage() {
    return {
      title: `AI风险分析：${this.data.indicatorName}`,
      path: '/pages/risk/risk',
    };
  },

  loadEval() {
    if (this.data.generating) return;
    
    const app = getApp();
    const companyId = app.globalData.companyInfo ? app.globalData.companyInfo.id : null;
    if (!companyId) {
      this.setData({ hasError: true, errorMsg: '用户信息异常，请重新登录' });
      return;
    }

    // 使用 riskIndex 调用 SSE 流式接口，传递指标信息
    const riskIndex = this.data.riskIndex || 1;
    
    // 停止之前的打字效果
    if (this.typingTimer) {
      clearTimeout(this.typingTimer);
    }
    
    this.setData({ 
      generating: true, 
      hasError: false, 
      evalContent: '', 
      fullContent: '',
      errorMsg: '',
      typingIndex: 0,
    });
    
    const token = wx.getStorageSync('access_token');
    const baseUrl = app.globalData.baseUrl || 'http://192.168.1.80:8000/api/v1';
    
    // 构建 URL 参数
    const params = [];
    if (this.data.indicatorName) {
      params.push(`indicator_name=${encodeURIComponent(this.data.indicatorName)}`);
    }
    if (this.data.level) {
      params.push(`level=${encodeURIComponent(this.data.level)}`);
    }
    if (this.data.reason) {
      params.push(`reason=${encodeURIComponent(this.data.reason)}`);
    }
    const queryString = params.length > 0 ? '?' + params.join('&') : '';
    
    wx.request({
      url: `${baseUrl}/miniapp/risk/ai-eval/${riskIndex}${queryString}`,
      method: 'GET',
      header: {
        'Authorization': `Bearer ${token}`,
      },
      timeout: 120000, // 120秒超时（AI模型响应较慢）
      success: (res) => {
        if (res.statusCode === 200 && res.data) {
          // 解析 SSE 格式内容
          let content = '';
          if (typeof res.data === 'string') {
            const lines = res.data.split('\n');
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') continue;
                try {
                  const parsed = JSON.parse(data);
                  // 优先取 content 字段（正文），忽略 reasoning_content（思考过程）
                  if (parsed.content) content += parsed.content;
                } catch (e) {
                  content += data;
                }
              }
            }
          } else if (res.data.content) {
            content = res.data.content;
          }

          if (content) {
            // 保存完整内容，开始打字机效果
            this.setData({ fullContent: content, generating: false });
            this.startTypingEffect();
          } else {
            this.setData({
              generating: false,
              evalContent: '暂无评估内容',
            });
          }
        } else {
          this.setData({
            generating: false,
            hasError: true,
            errorMsg: res.data?.detail || res.data?.message || 'AI评估失败，请稍后重试',
          });
        }
      },
      fail: (err) => {
        const msg = err.errMsg || '';
        let hint = '网络请求失败，请检查网络连接';
        if (msg.includes('timeout')) {
          hint = 'AI响应超时，请稍后重试（响应较慢属正常现象）';
        }
        this.setData({
          generating: false,
          hasError: true,
          errorMsg: hint,
        });
      },
    });
  },

  // 打字机效果
  startTypingEffect() {
    const { fullContent, typingIndex } = this.data;
    
    if (typingIndex >= fullContent.length) {
      // 打字完成
      this.setData({ evalContent: fullContent });
      return;
    }
    
    // 每次显示更多字符（加速效果）
    const chunkSize = typingIndex < 50 ? 1 : (typingIndex < 200 ? 3 : 5);
    const newIndex = Math.min(typingIndex + chunkSize, fullContent.length);
    const displayContent = fullContent.slice(0, newIndex);
    
    this.setData({
      typingIndex: newIndex,
      evalContent: displayContent,
    });
    
    // 继续打字
    const delay = typingIndex < 50 ? 30 : (typingIndex < 200 ? 15 : 8);
    this.typingTimer = setTimeout(() => {
      this.startTypingEffect();
    }, delay);
  },

  refreshEval() {
    wx.showModal({
      title: '重新生成',
      content: '确定要重新生成AI评估报告吗？',
      success: (res) => {
        if (res.confirm) this.loadEval();
      },
    });
  },

  goRiskList() {
    wx.navigateBack();
  },

  // 长按复制评估内容
  onLongPressContent() {
    if (!this.data.fullContent) return;
    wx.setClipboardData({
      data: this.data.fullContent,
      success() {
        wx.showToast({ title: '已复制到剪贴板', icon: 'success' });
      },
    });
  },
});
