import React, { useState } from 'react';
import { Card, Input, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useAtom } from 'jotai';
import {
  largeOrdersDataAtom,
  realtimeDataAtom
} from '../../../store/atoms';

const StockOrderDetails = () => {
  const [largeOrdersData] = useAtom(largeOrdersDataAtom);
  const [realtimeData] = useAtom(realtimeDataAtom);
  
  // 大单金额筛选状态
  const [amountFilters, setAmountFilters] = useState([300, 100, 50, 30]);
  
  // 表格排序和搜索状态
  const [sortField, setSortField] = useState('time');
  const [sortOrder, setSortOrder] = useState('desc');
  const [searchText, setSearchText] = useState('');

  // 处理金额筛选条件变化
  const handleAmountFilterChange = (amount) => {
    setAmountFilters(prev => {
      if (prev.includes(amount)) {
        return prev.filter(a => a !== amount);
      } else {
        return [...prev, amount];
      }
    });
  };

  // 全选/反选筛选条件
  const handleSelectAllFilters = () => {
    const allAmounts = [300, 100, 50, 30];
    if (amountFilters.length === allAmounts.length) {
      setAmountFilters([]);
    } else {
      setAmountFilters(allAmounts);
    }
  };

  // 获取各级别的统计数据
  const getAmountLevelStats = () => {
    if (!largeOrdersData || !largeOrdersData.largeOrders) return {};
    
    const orders = largeOrdersData.largeOrders;
    const stats = {
      300: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      100: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      50: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      30: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 }
    };

    orders.forEach(order => {
      const amountWan = order.amount / 10000;
      let level;
      
      if (amountWan >= 300) level = 300;
      else if (amountWan >= 100) level = 100;
      else if (amountWan >= 50) level = 50;
      else if (amountWan >= 30) level = 30;
      else return;

      if (order.type === 'buy') {
        stats[level].buy += 1;
        stats[level].buyAmount += amountWan;
      } else {
        stats[level].sell += 1;
        stats[level].sellAmount += amountWan;
      }
      stats[level].totalAmount += amountWan;
    });

    return stats;
  };

  // 获取实时统计数据
  const getRealtimeStats = () => {
    const stats = getAmountLevelStats();
    const totalOrders = Object.values(stats).reduce((sum, level) => sum + level.buy + level.sell, 0);
    const totalAmount = Object.values(stats).reduce((sum, level) => sum + level.totalAmount, 0);
    const buyOrders = Object.values(stats).reduce((sum, level) => sum + level.buy, 0);
    const sellOrders = Object.values(stats).reduce((sum, level) => sum + level.sell, 0);
    const buyAmount = Object.values(stats).reduce((sum, level) => sum + level.buyAmount, 0);
    const sellAmount = Object.values(stats).reduce((sum, level) => sum + level.sellAmount, 0);
    const netFlow = buyAmount - sellAmount;

    return {
      totalOrders,
      totalAmount,
      buyOrders,
      sellOrders,
      buyAmount,
      sellAmount,
      netFlow,
      buyRatio: totalOrders > 0 ? (buyOrders / totalOrders * 100) : 0
    };
  };

  // 排序功能
  const handleSort = (field) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const getFilteredTrades = () => {
    if (!largeOrdersData || !largeOrdersData.largeOrders) return [];
    
    let filtered = largeOrdersData.largeOrders.filter(trade => {
      const amountWan = trade.amount / 10000;
      
      const amountMatch = (
        (amountWan >= 300 && amountFilters.includes(300)) ||
        (amountWan >= 100 && amountWan < 300 && amountFilters.includes(100)) ||
        (amountWan >= 50 && amountWan < 100 && amountFilters.includes(50)) ||
        (amountWan >= 30 && amountWan < 50 && amountFilters.includes(30))
      );
      
      if (!amountMatch) return false;
      
      if (searchText) {
        const searchLower = searchText.toLowerCase();
        const searchMatch = (
          trade.time.includes(searchText) ||
          trade.price.toString().includes(searchText) ||
          trade.volume.toString().includes(searchText) ||
          (trade.amount / 10000).toFixed(2).includes(searchText) ||
          (trade.type === 'buy' ? '买' : '卖').includes(searchText)
        );
        
        if (!searchMatch) return false;
      }
      
      return true;
    }).map(trade => {
      const amountWan = trade.amount / 10000;
      let status;
      
      if (trade.type === 'buy') {
        status = amountWan >= 100 ? '主买' : '被买';
      } else {
        status = '主卖';
      }
      
      return {
        time: trade.time.includes(' ') ? trade.time.split(' ')[1] : trade.time,
        fullTime: trade.time,
        status: status,
        price: trade.price.toFixed(2),
        priceNum: trade.price,
        volume: trade.volume.toLocaleString(),
        volumeNum: trade.volume,
        amount: (trade.amount / 10000).toFixed(2),
        amountNum: trade.amount / 10000,
        type: trade.type,
        amountWan: trade.amount / 10000
      };
    });

    // 排序功能
    filtered.sort((a, b) => {
      let aValue, bValue;
      
      switch (sortField) {
        case 'time':
          aValue = a.fullTime;
          bValue = b.fullTime;
          break;
        case 'price':
          aValue = a.priceNum;
          bValue = b.priceNum;
          break;
        case 'volume':
          aValue = a.volumeNum;
          bValue = b.volumeNum;
          break;
        case 'amount':
          aValue = a.amountNum;
          bValue = b.amountNum;
          break;
        default:
          aValue = a.fullTime;
          bValue = b.fullTime;
      }
      
      if (sortOrder === 'asc') {
        return aValue > bValue ? 1 : -1;
      } else {
        return aValue < bValue ? 1 : -1;
      }
    });

    return filtered.slice(0, 50);
  };

  // 根据交易类型和金额获取样式类名
  const getTradeItemClass = (trade) => {
    const amountWan = parseFloat(trade.amount);
    let classes = [];
    
    if (trade.type === 'buy') {
      classes.push('trade-buy');
    } else {
      classes.push('trade-sell');
    }
    
    if (amountWan >= 300) {
      classes.push('level-300');
    } else if (amountWan >= 100) {
      classes.push('level-100');
    } else if (amountWan >= 50) {
      classes.push('level-50');
    } else if (amountWan >= 30) {
      classes.push('level-30');
    }
    
    return classes.join(' ');
  };

  return (
    <div>
      {/* 大单交易明细 */}
      {largeOrdersData && largeOrdersData.largeOrders && (
        <Card className="stock-card" title="大单交易明细">
          {/* 实时统计面板 */}
          <div className="realtime-stats-panel">
            <div className="stats-overview">
              <div className="overview-item">
                <div className="overview-label">总交易</div>
                <div className="overview-value">{getRealtimeStats().totalOrders} 笔</div>
              </div>
              <div className="overview-item">
                <div className="overview-label">总金额</div>
                <div className="overview-value">{getRealtimeStats().totalAmount.toFixed(0)} 万</div>
              </div>
              <div className="overview-item">
                <div className="overview-label">净流入</div>
                <div className={`overview-value ${getRealtimeStats().netFlow >= 0 ? 'positive' : 'negative'}`}>
                  {getRealtimeStats().netFlow >= 0 ? '+' : ''}{getRealtimeStats().netFlow.toFixed(0)} 万
                </div>
              </div>
              <div className="overview-item">
                <div className="overview-label">买入占比</div>
                <div className={`overview-value ${getRealtimeStats().buyRatio >= 50 ? 'positive' : 'negative'}`}>
                  {getRealtimeStats().buyRatio.toFixed(1)}%
                </div>
              </div>
            </div>
            
            <div className="level-distribution">
              {[
                { amount: 300, label: '≥300万', color: '#ff1744' },
                { amount: 100, label: '≥100万', color: '#ff6600' },
                { amount: 50, label: '≥50万', color: '#ff9900' },
                { amount: 30, label: '≥30万', color: '#ffc107' }
              ].map(item => {
                const stats = getAmountLevelStats()[item.amount] || { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 };
                const total = stats.buy + stats.sell;
                const buyPercentage = total > 0 ? (stats.buy / total * 100) : 0;
                
                return (
                  <div key={item.amount} className="distribution-item">
                    <div className="distribution-header">
                      <span className="distribution-label" style={{ color: item.color }}>
                        {item.label}
                      </span>
                      <span className="distribution-total">{total} 笔</span>
                    </div>
                    <div className="distribution-bar">
                      <div 
                        className="bar-buy" 
                        style={{ 
                          width: `${buyPercentage}%`,
                          backgroundColor: item.color,
                          opacity: 0.8
                        }}
                      ></div>
                      <div 
                        className="bar-sell" 
                        style={{ 
                          width: `${100 - buyPercentage}%`,
                          backgroundColor: '#52c41a',
                          opacity: 0.8
                        }}
                      ></div>
                    </div>
                    <div className="distribution-details">
                      <span className="detail-buy">买 {stats.buy} ({stats.buyAmount.toFixed(0)}万)</span>
                      <span className="detail-sell">卖 {stats.sell} ({stats.sellAmount.toFixed(0)}万)</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 增强的筛选控件 */}
          <div className="trade-filters-enhanced">
            <div className="filter-header">
              <div className="filter-title">
                <span>大单筛选</span>
                <span className="filter-count">
                  已选 {amountFilters.length}/4 项，共 {getFilteredTrades().length} 笔交易
                </span>
              </div>
              <div className="filter-actions">
                <Button 
                  type="text" 
                  size="small" 
                  onClick={handleSelectAllFilters}
                  style={{ color: '#1890ff' }}
                >
                  {amountFilters.length === 4 ? '取消全选' : '全选'}
                </Button>
              </div>
            </div>
            
            <div className="filter-level-grid">
              {[
                { amount: 300, label: '≥300万', color: '#ff1744', desc: '超大单' },
                { amount: 100, label: '≥100万', color: '#ff6600', desc: '大单' },
                { amount: 50, label: '≥50万', color: '#ff9900', desc: '中单' },
                { amount: 30, label: '≥30万', color: '#52c41a', desc: '小单' }
              ].map(item => {
                const stats = getAmountLevelStats()[item.amount] || { buy: 0, sell: 0, totalAmount: 0 };
                const isChecked = amountFilters.includes(item.amount);
                
                return (
                  <div 
                    key={item.amount}
                    className={`filter-level-item ${isChecked ? 'active' : ''}`}
                    onClick={() => handleAmountFilterChange(item.amount)}
                  >
                    <div className="level-header">
                      <div className="level-checkbox">
                        <input 
                          type="checkbox" 
                          checked={isChecked}
                          onChange={() => {}}
                          style={{ accentColor: item.color }}
                        />
                        <span className="level-label" style={{ color: item.color }}>
                          {item.label}
                        </span>
                        <span className="level-desc">{item.desc}</span>
                      </div>
                    </div>
                    <div className="level-stats">
                      <div className="stat-row">
                        <span className="stat-buy">买 {stats.buy}</span>
                        <span className="stat-sell">卖 {stats.sell}</span>
                      </div>
                      <div className="stat-amount">
                        合计 {stats.totalAmount.toFixed(0)}万
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 搜索栏 */}
          <div className="trade-search">
            <Input
              placeholder="搜索时间、价格、金额或交易类型..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
              allowClear
              style={{ 
                backgroundColor: '#2a2a2a', 
                borderColor: '#444', 
                color: '#fff',
                marginBottom: '12px'
              }}
            />
          </div>

          {/* 可排序的表头 */}
          <div className="trade-header sortable">
            <div 
              className={`header-item time sortable ${sortField === 'time' ? 'active' : ''}`}
              onClick={() => handleSort('time')}
            >
              时间
              {sortField === 'time' && (
                <span className="sort-indicator">
                  {sortOrder === 'asc' ? ' ↑' : ' ↓'}
                </span>
              )}
            </div>
            <div className="header-item status">状态</div>
            <div 
              className={`header-item price sortable ${sortField === 'price' ? 'active' : ''}`}
              onClick={() => handleSort('price')}
            >
              价格
              {sortField === 'price' && (
                <span className="sort-indicator">
                  {sortOrder === 'asc' ? ' ↑' : ' ↓'}
                </span>
              )}
            </div>
            <div 
              className={`header-item volume sortable ${sortField === 'volume' ? 'active' : ''}`}
              onClick={() => handleSort('volume')}
            >
              手数
              {sortField === 'volume' && (
                <span className="sort-indicator">
                  {sortOrder === 'asc' ? ' ↑' : ' ↓'}
                </span>
              )}
            </div>
            <div 
              className={`header-item amount sortable ${sortField === 'amount' ? 'active' : ''}`}
              onClick={() => handleSort('amount')}
            >
              金额(万)
              {sortField === 'amount' && (
                <span className="sort-indicator">
                  {sortOrder === 'asc' ? ' ↑' : ' ↓'}
                </span>
              )}
            </div>
          </div>

          {/* 交易明细列表 */}
          <div className="trade-list">
            {getFilteredTrades().map((trade, index) => (
              <div 
                key={`${trade.time}-${index}`} 
                className={`trade-item ${getTradeItemClass(trade)}`}
              >
                <div className="trade-time">{trade.time}</div>
                <div className="trade-status">{trade.status}</div>
                <div className="trade-price">{trade.price}</div>
                <div className="trade-volume">{trade.volume}</div>
                <div className="trade-amount">{trade.amount}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 实时交易数据 */}
      {realtimeData && realtimeData.recentTrades && (
        <Card className="stock-card" title="实时交易数据">
          {/* 表头 */}
          <div className="trade-header">
            <div className="header-item time">时间</div>
            <div className="header-item status">性质</div>
            <div className="header-item price">价格</div>
            <div className="header-item volume">手数</div>
            <div className="header-item amount">金额(万)</div>
          </div>

          {/* 实时交易列表 */}
          <div className="trade-list" style={{ maxHeight: '300px' }}>
            {realtimeData.recentTrades.map((trade, index) => (
              <div 
                key={`${trade.time}-${index}`} 
                className={`trade-item ${trade.buy ? 'trade-buy' : 'trade-sell'}`}
              >
                <div className="trade-time">{trade.time}</div>
                <div className="trade-status">{trade.buy ? '买盘' : '卖盘'}</div>
                <div className="trade-price">¥{trade.price.toFixed(2)}</div>
                <div className="trade-volume">{trade.volume.toLocaleString()}</div>
                <div className="trade-amount">{(trade.amount / 10000).toFixed(2)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default StockOrderDetails; 