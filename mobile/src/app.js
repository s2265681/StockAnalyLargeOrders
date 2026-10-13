// 百度移动统计（Taro 需在 app 入口最顶部引入，见 docs.taro.zone/docs/report）
import './utils/mtj-wx-sdk'
import { useLaunch } from '@tarojs/taro'
import './app.scss'

function App({ children }) {
  useLaunch(() => {
    // 应用启动
  })

  return children
}

export default App
