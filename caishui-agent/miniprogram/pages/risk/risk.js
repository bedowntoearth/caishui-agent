// pages/risk/risk.js
const { get } = require('../../utils/request');
const { getRiskLevelInfo } = require('../../utils/util');

Page({
  data: {
    loading: true,
    hasData: false,
    indicators: [],
    period: '',
    healthScore: 100,
    companyInfo: null,
  },

  onLoad() {
    const app = getApp();
    const companyId = app.globalData.companyInfo ? app.globalData.companyInfo.id : null;
    if (!companyId) {
      // companyInfo 未缓存，重新获取
      this.loadCompanyThenRisk();
    } else {
      this.loadRiskIndicators(companyId);
    }
  },

  async loadCompanyThenRisk() {
    try {
      const companyInfo = await get('/miniapp/company/info');
      getApp().globalData.companyInfo = companyInfo;
      this.loadRiskIndicators(companyInfo.id);
    } catch (e) {
      this.setData({ loading: false, hasData: false });
    }
  },

  onPullDownRefresh() {
    const app = getApp();
    const companyId = app.globalData.companyInfo ? app.globalData.companyInfo.id : null;
    if (companyId) {
      this.loadRiskIndicators(companyId);
    } else {
      this.loadCompanyThenRisk();
    }
    wx.stopPullDownRefresh();
  },

  async loadRiskIndicators(companyId) {
    this.setData({ loading: true });
    try {
      // 注意：后端从 JWT token 中解析 company_id，参数中的 company_id 被忽略
      const data = await get(`/miniapp/risk/indicators`);
      const indicators = (data.indicators || []).map((ind, index) => ({
        ...ind,
        index,
        levelInfo: getRiskLevelInfo(ind.level),
      }));

      // 按风险等级排序：major > warning > remind > normal
      const order = { major_risk: 0, warning: 1, remind: 2, normal: 3 };
      indicators.sort((a, b) => (order[a.level] || 3) - (order[b.level] || 3));

      // 排序后重新计算 index（使用排序后的位置，与用户看到的顺序一致）
      indicators.forEach((ind, i) => { ind.index = i; });

      // 使用后端返回的健康评分（与后端计算保持一致）
      const healthScore = data.health_score || 0;

      this.setData({
        loading: false,
        hasData: indicators.length > 0,
        indicators,
        period: data.period || '',
        healthScore,
      });
    } catch (e) {
      this.setData({ loading: false, hasData: false });
    }
  },

  onTapIndicator(e) {
    const index = e.currentTarget.dataset.index;
    const indicator = this.data.indicators[index];
    // 只有非正常等级才跳转AI评估
    if (indicator.level === 'normal') {
      wx.showToast({ title: '该指标状态正常', icon: 'success' });
      return;
    }
    wx.navigateTo({
      url: `/pages/ai-eval/ai-eval?indicatorId=${indicator.id}&indicatorName=${encodeURIComponent(indicator.name)}&level=${indicator.level}&reason=${encodeURIComponent(indicator.reason || '')}&riskIndex=${indicator.index}`,
    });
  },
});
