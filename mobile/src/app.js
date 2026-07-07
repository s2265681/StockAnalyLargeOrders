import { useLaunch } from '@tarojs/taro'
import './app.scss'

function App({ children }) {
  useLaunch(() => {
    // 应用启动
  })

  return children
}

export default App
