import React from 'react';
import { Alert, Card, Empty, Tag } from 'antd';
import { useAtom } from 'jotai';
import { limitUpThemesAtom } from '../../../store/atoms';

const formatAmount = (value) => {
  const amount = Number(value || 0);
  if (!amount) return '--';
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(2)}亿`;
  return `${(amount / 10000).toFixed(0)}万`;
};

const ThemeLimitUpPanel = () => {
  const [data] = useAtom(limitUpThemesAtom);

  if (!data) {
    return null;
  }

  if (data.error) {
    return (
      <Card className="stock-card theme-limit-card" title="题材与涨停归纳">
        <Alert type="warning" showIcon message="涨停题材数据暂不可用" description={data.error} />
      </Card>
    );
  }

  const currentStock = data.current_stock || {};
  const themes = data.themes || [];
  const echelonTheme = data.echelon_theme || data.current_theme;
  const echelonCount = data.echelon_theme_count ?? data.current_theme_count;
  const currentThemeText = echelonTheme
    ? `当前股票属于涨停梯队【${echelonTheme}】题材，当天该题材有 ${echelonCount || 0} 家涨停`
    : currentStock.reason || '当前股票未在当日涨停池中，暂无涨停原因';

  const sentiment = data.market_sentiment || {};
  const sentimentColor = {
    '强势': '#ff4d4f',
    '偏强': '#faad14',
    '中性': '#1890ff',
    '偏弱': '#52c41a',
  }[sentiment.sentiment_label] || '#999';

  const linkageColor = (label) => {
    if (label === '强联动') return '#52c41a';
    if (label === '中等联动') return '#faad14';
    return '#999';
  };

  return (
    <Card className="stock-card theme-limit-card" title="题材与涨停归纳">
      {sentiment.sentiment_label && (
        <div className="market-sentiment-bar" style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '6px 12px', marginBottom: 8,
          background: 'rgba(255,255,255,0.04)', borderRadius: 4,
        }}>
          <Tag color={sentimentColor}>{sentiment.sentiment_label}</Tag>
          {sentiment.emotion_stage && (
            <span style={{ color: '#999', fontSize: 12 }}>情绪 {sentiment.emotion_stage}</span>
          )}
          <span style={{ color: '#ff4d4f' }}>涨停 {sentiment.limit_up_count}</span>
          <span style={{ color: '#52c41a' }}>跌停 {sentiment.limit_down_count}</span>
          {(sentiment.lone_wolf_stocks || []).length > 0 && (
            <span style={{ color: '#faad14', fontSize: 12 }}>
              独狼 {sentiment.lone_wolf_stocks.length} 只
            </span>
          )}
        </div>
      )}
      <div className="theme-current-box">
        <div className="theme-current-title">
          {currentStock.name || currentStock.code || '当前股票'}
          {echelonTheme && <Tag color="red">{echelonTheme}</Tag>}
        </div>
        <div className="theme-current-reason">{currentThemeText}</div>
        <div className="theme-current-note">{data.note}</div>
      </div>

      {themes.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无涨停池数据" />
      ) : (
        <div className="theme-rank-list">
          {themes.map((theme) => (
            <div className="theme-rank-item" key={theme.theme}>
              <div className="theme-rank-header">
                <span className="theme-rank-name">{theme.theme}</span>
                <span className="theme-rank-count">涨停 {theme.count} 家</span>
                {theme.linkage_label && (
                  <Tag color={linkageColor(theme.linkage_label)} style={{ marginLeft: 4, fontSize: 11 }}>
                    {theme.linkage_label}
                  </Tag>
                )}
              </div>
              <div className="theme-stock-list">
                {(theme.stocks || []).slice(0, 8).map((stock) => (
                  <span
                    className={`theme-stock-chip ${stock.code === currentStock.code ? 'active' : ''}`}
                    key={stock.code}
                    title={`${stock.name} ${stock.reason}`}
                  >
                    {stock.name}
                    <em>{stock.consecutive_boards || 1}板</em>
                    <small>{formatAmount(stock.seal_amount)}</small>
                  </span>
                ))}
                {(theme.stocks || []).length > 8 && (
                  <span className="theme-stock-more">+{theme.stocks.length - 8}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

export default ThemeLimitUpPanel;
