import React, { useEffect, useState } from 'react';
import { AutoComplete, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useAtom } from 'jotai';
import {
  stockCodeAtom,
  stockBasicDataAtom,
  errorAtom,
  fetchStockBasicAtom
} from '../../../store/atoms';
import { apiRequest } from '../../../config/api';

const StockBasicInfo = ({ onStockCodeChange }) => {
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [stockBasicData] = useAtom(stockBasicDataAtom);
  const [, fetchStockBasic] = useAtom(fetchStockBasicAtom);
  const [_innerCode, setInnerCode] = useState(stockCode);
  
  // 股票搜索相关状态
  const [searchOptions, setSearchOptions] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // 股票搜索功能
  const handleStockSearch = async (value) => {
    
  };

  // 股票代码搜索
  const handleSearch = (value) => {
      setInnerCode(value)
  };

  // 点击搜索图标触发搜索
  const handleSearchIconClick = () => {
    onStockCodeChange(_innerCode);

  };

  // 选择搜索建议时的处理
  const handleSearchSelect = (value, option) => {
    setStockCode(value);
    handleSearch(value);
    setSearchOptions([]);
  };

  //调用basic 接口数据
  useEffect(()=>{
    fetchStockBasic(stockCode)
  },[fetchStockBasic, stockCode])

  console.log(stockCode,'stockCode;;;;')

  return (
    <div className=''>
      {/* 股票基础信息 - 新样式 */}
      {stockBasicData && (
        <div className="stock-header-new">
          {/* 顶部：股票名称和代码 */}
          <div className="stock-title-bar">
            <div className="stock-name-code">
              <span className="stock-name">{stockBasicData.name}</span>
              <span className="stock-code">{stockBasicData.code}</span>
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

          {/* 中部：当前价格和涨跌幅 */}
          <div className="price-section">
            <div className="main-price">
              <span className="label">当前价格</span>
              <span 
                className={`price ${stockBasicData.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData.current_price}
              </span>
              <span 
                className={`change ${stockBasicData.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData.change_percent >= 0 ? '+' : ''}{stockBasicData.change_percent}%
              </span>
            </div>
          </div>

          {/* 底部：基本数据 */}
          <div className="basic-stats">
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">开</span>
                <span className="value">{stockBasicData.open}</span>
              </div>
              <div className="stat-item">
                <span className="label">高</span>
                <span className="value">{stockBasicData.high}</span>
              </div>
              <div className="stat-item">
                <span className="label">量</span>
                <span className="value">{(stockBasicData.volume / 10000).toFixed(2)}</span>
              </div>
            </div>
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">昨</span>
                <span className="value">{stockBasicData.yesterday_close}</span>
              </div>
              <div className="stat-item">
                <span className="label">低</span>
                <span className="value">{stockBasicData.low}</span>
              </div>
              <div className="stat-item">
                <span className="label">额</span>
                <span className="value">{(stockBasicData.turnover / 100000000).toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StockBasicInfo; 