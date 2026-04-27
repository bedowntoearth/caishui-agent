// pages/index/index.js
const app = getApp()

Page({
  data: {
    companyInfo: null,
    healthScore: 0,
    healthLevel: '',
    isExpiringSoon: false,
    daysRemaining: 0,
  },

  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: '/pages/login/login' })
      return
    }
    this.loadData()
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh())
  },

  async loadData() {
    wx.showNavigationBarLoading()
    try {
      const companyData = await app.getCompanyInfo()
      this.setData({
        companyInfo: companyData,
        isExpiringSoon: companyData.is_expiring_soon || false,
        daysRemaining: companyData.days_remaining || 0,
      })

      // 获取风险指标
      await this.loadRiskIndicators()
    } catch (err) {
      console.error('加载数据失败:', err)
      if (err.message.includes('未找到')) {
        wx.showModal({ title: '提示', content: '暂无关联企业信息', showCancel: false })
      }
    } finally {
      wx.hideNavigationBarLoading()
    }
  },

  async loadRiskIndicators() {
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${app.globalData.baseUrl}/miniapp/risk/indicators`,
        header: { 'Authorization': `Bearer ${app.globalData.token}` },
        success: res => {
          if (res.statusCode === 200 && res.data.has_data) {
            const score = res.data.health_score
            let level = '优秀'
            if (score < 60) level = '较差'
            else if (score < 75) level = '一般'
            else if (score < 90) level = '良好'

            this.setData({ healthScore: score, healthLevel: level })
          } else {
            this.setData({ healthScore: -1, healthLevel: '暂无数据' })
          }
          resolve()
        },
        fail: reject
      })
    })
  },

  goToRisk() {
    wx.switchTab({ url: '/pages/risk/risk' })
  },

  goToAiEval() {
    wx.switchTab({ url: '/pages/risk/risk' })
  },
})
