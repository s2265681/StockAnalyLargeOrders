export default defineAppConfig({
  pages: [
    'pages/login/index',
    'pages/register/index',
    'pages/stock-dashboard/index',
    'pages/limit-up-echelon/index',
    'pages/emotion-cycle/index',
    'pages/auction-grab/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'AI炒股指南',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#8a8a8a',
    selectedColor: '#d97706',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/stock-dashboard/index', text: '个股', iconPath: 'assets/tabbar/stock.png', selectedIconPath: 'assets/tabbar/stock_on.png' },
      { pagePath: 'pages/limit-up-echelon/index', text: '梯队', iconPath: 'assets/tabbar/echelon.png', selectedIconPath: 'assets/tabbar/echelon_on.png' },
      { pagePath: 'pages/emotion-cycle/index', text: '情绪', iconPath: 'assets/tabbar/emotion.png', selectedIconPath: 'assets/tabbar/emotion_on.png' },
      { pagePath: 'pages/auction-grab/index', text: '竞价', iconPath: 'assets/tabbar/auction.png', selectedIconPath: 'assets/tabbar/auction_on.png' },
    ],
  },
})
