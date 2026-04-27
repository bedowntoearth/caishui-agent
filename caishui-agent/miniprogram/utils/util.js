/**
 * 工具函数集合
 */

/**
 * 格式化日期时间
 * @param {string|Date} date
 * @param {string} fmt
 */
function formatDate(date, fmt = 'YYYY-MM-DD') {
  if (!date) return '--';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '--';
  const map = {
    'YYYY': d.getFullYear(),
    'MM': String(d.getMonth() + 1).padStart(2, '0'),
    'DD': String(d.getDate()).padStart(2, '0'),
    'HH': String(d.getHours()).padStart(2, '0'),
    'mm': String(d.getMinutes()).padStart(2, '0'),
    'ss': String(d.getSeconds()).padStart(2, '0'),
  };
  return fmt.replace(/YYYY|MM|DD|HH|mm|ss/g, matched => map[matched]);
}

/**
 * 风险等级配置
 */
const RISK_LEVEL_CONFIG = {
  normal:     { text: '正常',     cls: 'badge-normal',     color: '#28c76f', bgClass: 'success' },
  remind:     { text: '提醒',     cls: 'badge-remind',     color: '#ff9f43', bgClass: 'orange' },
  warning:    { text: '预警',     cls: 'badge-warning',    color: '#ffbe00', bgClass: 'warning' },
  major_risk: { text: '重大风险', cls: 'badge-major',      color: '#ea5455', bgClass: 'danger' },
};

function getRiskLevelInfo(level) {
  return RISK_LEVEL_CONFIG[level] || RISK_LEVEL_CONFIG.normal;
}

/**
 * 健康评分计算（前端预估，供展示用）
 * 基于指标等级分布进行简单加权
 */
function calcHealthScore(indicators) {
  if (!indicators || !indicators.length) return 100;
  const weights = { normal: 100, remind: 60, warning: 30, major_risk: 0 };
  const total = indicators.reduce((sum, ind) => sum + (weights[ind.level] || 100), 0);
  return Math.round(total / indicators.length);
}

/**
 * 手机号脱敏
 */
function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone;
  return phone.slice(0, 3) + '****' + phone.slice(-4);
}

/**
 * 截断文本
 */
function truncate(str, maxLen = 50) {
  if (!str) return '';
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str;
}

/**
 * 防抖
 */
function debounce(fn, delay = 300) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

module.exports = {
  formatDate,
  getRiskLevelInfo,
  calcHealthScore,
  maskPhone,
  truncate,
  debounce,
  RISK_LEVEL_CONFIG,
};
