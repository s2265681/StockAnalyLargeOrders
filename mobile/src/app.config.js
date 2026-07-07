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
      { pagePath: 'pages/stock-dashboard/index', text: '个股' },
      { pagePath: 'pages/limit-up-echelon/index', text: '梯队' },
      { pagePath: 'pages/emotion-cycle/index', text: '情绪' },
      { pagePath: 'pages/auction-grab/index', text: '竞价' },
    ],
  },
})
