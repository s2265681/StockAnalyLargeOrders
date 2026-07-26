export default defineAppConfig({
  pages: [
    'pages/home/index',
    'pages/membership/index',
    'pages/mine/index',
    'pages/login/index',
    'pages/register/index',
    'pages/stock-dashboard/index',
    'pages/limit-up-echelon/index',
    'pages/dragon-tiger/index',
    'pages/emotion-cycle/index',
    'pages/auction-grab/index',
    'pages/sector-grab/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: '重阳市场看板助手',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#8a8a8a',
    selectedColor: '#d97706',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/home/index', text: '首页', iconPath: 'assets/tabbar/home.png', selectedIconPath: 'assets/tabbar/home_on.png' },
      { pagePath: 'pages/membership/index', text: '会员', iconPath: 'assets/tabbar/vip.png', selectedIconPath: 'assets/tabbar/vip_on.png' },
      { pagePath: 'pages/mine/index', text: '我的', iconPath: 'assets/tabbar/mine.png', selectedIconPath: 'assets/tabbar/mine_on.png' },
    ],
  },
})
