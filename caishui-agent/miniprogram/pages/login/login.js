// pages/login/login.js
const app = getApp()

Page({
  data: {
    loading: false,
    canGetPhone: true,
  },

  onLoad() {
    // 如果已有token，直接跳转首页
    if (app.globalData.token) {
      this.redirectToHome()
      return
    }
  },

  async getPhoneNumber(e) {
    if (!e.detail.code || !e.detail.iv) {
      wx.showToast({ title: '请授权手机号', icon: 'none' })
      return
    }

    if (this.data.loading) return
    this.setData({ loading: true })

    try {
      // 先获取微信登录code
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: reject
        })
      })

      const code = loginRes.code

      // 调用后端登录接口
      const res = await new Promise((resolve, reject) => {
        wx.request({
          url: `${app.globalData.baseUrl}/miniapp/login`,
          method: 'POST',
          data: {
            code: code,
            encrypted_data: e.detail.encryptedData || '',
            iv: e.detail.iv || ''
          },
          success: resolve,
          fail: reject
        })
      })

      if (res.statusCode === 200 && res.data.access_token) {
        const tokenData = res.data
        app.globalData.token = tokenData.access_token
        wx.setStorageSync('access_token', tokenData.access_token)

        if (tokenData.is_matched && tokenData.company_id) {
          await app.getCompanyInfo()
          this.redirectToHome()
        } else {
          wx.showModal({
            title: '未匹配企业',
            content: '您的手机号尚未关联到任何企业，请联系财税公司运营人员确认',
            showCancel: false,
            confirmText: '我知道了'
          })
        }
      } else {
        wx.showToast({
          title: res.data.detail || '登录失败',
          icon: 'none'
        })
      }
    } catch (err) {
      console.error('登录失败:', err)
      wx.showToast({ title: '网络错误，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  redirectToHome() {
    wx.switchTab({ url: '/pages/index/index' })
  },
})
