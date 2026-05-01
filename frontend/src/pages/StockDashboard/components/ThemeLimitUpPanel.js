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
  const currentThemeText = data.current_theme
    ? `当前股票属于${data.current_theme}题材，当天该题材有${data.current_theme_count || 0}家涨停`
    : currentStock.reason || '当前股票未在当日涨停池中，暂无涨停原因';

  return (
    <Card className="stock-card theme-limit-card" title="题材与涨停归纳">
      <div className="theme-current-box">
        <div className="theme-current-title">
          {currentStock.name || currentStock.code || '当前股票'}
          {data.current_theme && <Tag color="red">{data.current_theme}</Tag>}
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
