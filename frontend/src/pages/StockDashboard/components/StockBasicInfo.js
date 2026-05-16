/* eslint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useState } from 'react';
import { AutoComplete, Input, Tooltip } from 'antd';
import { SearchOutlined, ThunderboltOutlined, LoadingOutlined } from '@ant-design/icons';
import { useAtom } from 'jotai';
import {
  stockCodeAtom,
  stockBasicDataAtom,
  fetchStockBasicAtom
} from '../../../store/atoms';
import LimitUpMonitorPanel from './LimitUpMonitorPanel';
import { apiRequest } from '../../../config/api';

const StockBasicInfo = ({ onStockCodeChange }) => {
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [stockBasicData] = useAtom(stockBasicDataAtom);
  const [, fetchStockBasic] = useAtom(fetchStockBasicAtom);
  const [_innerCode, setInnerCode] = useState(stockCode);
  const [themeTags, setThemeTags] = useState([]);
  const [themeLoading, setThemeLoading] = useState(false);

  // 股票搜索相关状态
  const [searchOptions, setSearchOptions] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // 切换股票时清空题材标签
  useEffect(() => { setThemeTags([]); }, [stockCode]);

  // 股票代码搜索
  const handleSearch = (value) => {
      setInnerCode(value)
  };

  // 点击搜索图标触发搜索
  const handleSearchIconClick = () => {
    onStockCodeChange(_innerCode);
  };

  //调用basic 接口数据
  useEffect(()=>{
    fetchStockBasic(stockCode)
  },[stockCode])

  const fetchThemeTags = async () => {
    if (!stockCode || themeLoading) return;
    setThemeLoading(true);
    try {
      const today = new Date();
      const dow = today.getDay();
      if (dow === 6) today.setDate(today.getDate() - 1);
      if (dow === 0) today.setDate(today.getDate() - 2);
      const dt = `${today.getFullYear()}${String(today.getMonth()+1).padStart(2,'0')}${String(today.getDate()).padStart(2,'0')}`;
      const res = await apiRequest(`/api/v1/stock-theme-tags?code=${stockCode}&dt=${dt}&industry=${encodeURIComponent(stockBasicData?.industry || '')}`);
      if (res?.data?.tags) {
        setThemeTags(res.data.tags);
      }
    } catch (e) {
      console.error('题材标签获取失败', e);
    } finally {
      setThemeLoading(false);
    }
  };

  const tagColors = {
    theme: { bg: '#1a2f1a', border: '#2a6b4a', text: '#10b981' },
    industry: { bg: '#1a1f2f', border: '#2a3a6b', text: '#60a5fa' },
  };

  return (
    <div className=''>
      {/* 股票基础信息 - 新样式 */}
        <div className="stock-header-new">
          {/* 顶部：股票名称和代码 */}
          <div className="stock-title-bar">
            <div className="stock-name-code">
              <span className="stock-name">{stockBasicData?.name}</span>
                  {/* 中部：当前价格和涨跌幅 */}
            <div className="main-price">
              <span className="label">当前价格</span>
              <span
                className={`price ${stockBasicData?.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData?.current_price ?? stockBasicData?.price}
              </span>
              <span
                className={`change ${stockBasicData?.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData?.change_percent >= 0 ? '+' : ''}{stockBasicData?.change_percent}%
              </span>
              {/* 智能题材按钮 + 标签结果 */}
              <div className="smart-theme-area">
                <Tooltip title="智能分析今日题材归属及同类涨停数">
                  <button
                    className={`smart-theme-btn ${themeLoading ? 'loading' : ''}`}
                    onClick={fetchThemeTags}
                    disabled={themeLoading}
                  >
                    {themeLoading
                      ? <LoadingOutlined style={{ marginRight: 4 }} />
                      : <ThunderboltOutlined style={{ marginRight: 4 }} />
                    }
                    题材
                  </button>
                </Tooltip>
                {themeTags.map((tag) => {
                  const c = tagColors[tag.type] || tagColors.industry;
                  return (
                    <Tooltip key={tag.label} title={tag.reason || ''}>
                      <span
                        className="smart-theme-tag"
                        style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
                      >
                        {tag.label}
                        <em className="smart-theme-count">{tag.count}</em>
                      </span>
                    </Tooltip>
                  );
                })}
              </div>
            </div>

              {/* <span className="stock-code">{stockBasicData.code}</span> */}
            </div>
            <div className="search-box">
              <AutoComplete
                value={_innerCode}
                options={searchOptions}
                // onSearch={handleStockSearch}
                // onSelect={handleSearchSelect}
                onChange={(value) => {
                  setInnerCode(value)
                }}
                style={{ width: 200 }}
                placeholder="输入股票代码或名称搜索"
                // allowClear
              >
                <Input
                  onPressEnter={(e) => {
                    setInnerCode(e.target.value)
                  }}
                  style={{ 
                    backgroundColor: '#2a2a2a', 
                    borderColor: '#444', 
                    color: '#fff' 
                  }}
                  suffix={
                    <SearchOutlined 
                      style={{ color: '#fff', cursor: 'pointer' }} 
                      onClick={()=>{
                        onStockCodeChange(_innerCode)
                      }}
                    />
                  }
                  loading={searchLoading}
                />
              </AutoComplete>
            </div>
          </div>

      
          {/* 底部：基本数据 */}
          <div className="basic-stats">
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">开</span>
                <span className="value">{stockBasicData?.open}</span>
              </div>
              <div className="stat-item">
                <span className="label">高</span>
                <span className="value">{stockBasicData?.high}</span>
              </div>
              <div className="stat-item">
                <span className="label">量</span>
                <span className="value">{(stockBasicData?.volume / 10000).toFixed(2)}</span>
              </div>
            </div>
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">昨</span>
                <span className="value">{stockBasicData?.yesterday_close}</span>
              </div>
              <div className="stat-item">
                <span className="label">低</span>
                <span className="value">{stockBasicData?.low}</span>
              </div>
              <div className="stat-item">
                <span className="label">额</span>
                <span className="value">{(stockBasicData?.turnover / 100000000).toFixed(2)}</span>
              </div>
            </div>
          </div>
          <LimitUpMonitorPanel />
        </div>
    </div>
  );
};

export default StockBasicInfo; 