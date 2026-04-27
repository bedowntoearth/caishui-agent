// app.js
App({
  globalData: {
    userInfo: null,
    token: null,
    companyInfo: null,
    baseUrl: 'http://192.168.1.80:8000/api/v1', // 本地真机调试
  },
  onLaunch() {
    const token = wx.getStorageSync('access_token')
    if (token) {
      this.globalData.token = token
      this.checkLoginStatus()
    }
  },

  checkLoginStatus() {
    if (this.globalData.token) {
      this.getCompanyInfo()
    }
  },

  getCompanyInfo() {
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${this.globalData.baseUrl}/miniapp/company/info`,
        header: { 'Authorization': `Bearer ${this.globalData.token}` },
        success: res => {
          if (res.statusCode === 200 && res.data) {
            this.globalData.companyInfo = res.data
            resolve(res.data)
          } else {
            reject(new Error('获取企业信息失败'))
          }
        },
        fail: reject
      })
    })
  },

  showToast(title, icon = 'none') {
    wx.showToast({ title, icon, duration: 2000 })
  }
})
