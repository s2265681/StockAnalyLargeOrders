module.exports = {
  env: {
    NODE_ENV: '"production"',
  },
  defineConstants: {},
  mini: {},
  h5: {
    /**
     * 生产环境把请求打到同域，交给 Nginx 反代到后端；
     * 小程序端直接请求 https://www.stockai.xin（见 src/config/api.js）。
     */
  },
}
