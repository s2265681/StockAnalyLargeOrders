import React from 'react';
import { Tag, Progress } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { useAtom } from 'jotai';
import { limitUpMonitorAtom } from '../../../store/atoms';

const LimitUpMonitorPanel = () => {
  const [data] = useAtom(limitUpMonitorAtom);

  if (!data || !data.is_limit_up) {
    return null;
  }

  const trendIcon = data.seal_trend > 0.1
    ? <ArrowUpOutlined style={{ color: '#52c41a' }} />
    : data.seal_trend < -0.1
      ? <ArrowDownOutlined style={{ color: '#ff4d4f' }} />
      : <MinusOutlined style={{ color: '#faad14' }} />;

  const trendColor = data.seal_trend > 0.1 ? '#52c41a' : data.seal_trend < -0.1 ? '#ff4d4f' : '#faad14';

  return (
    <div className="limit-up-monitor">
      <div className="limit-up-header">
        <Tag color="red">涨停</Tag>
        <span className="limit-up-price">{data.limit_up_price}</span>
        {data.first_limit_time && (
          <span className="limit-up-time">首封 {data.first_limit_time}</span>
        )}
        {data.break_count > 0 && (
          <Tag color="orange">炸板 {data.break_count} 次</Tag>
        )}
      </div>
      <div className="limit-up-stats">
        <div className="seal-info">
          <span className="label">封单</span>
          <span className="value">{data.seal_amount.toFixed(0)}万</span>
          <span className="label" style={{ marginLeft: 12 }}>封单比</span>
          <Progress
            percent={Math.min(data.seal_ratio * 100, 100)}
            size="small"
            format={() => `${(data.seal_ratio * 100).toFixed(2)}%`}
            style={{ width: 120, display: 'inline-flex', marginLeft: 4 }}
          />
        </div>
        <div className="seal-trend">
          <span className="label">趋势</span>
          {trendIcon}
          <span style={{ color: trendColor, marginLeft: 4 }}>{data.seal_trend_label}</span>
        </div>
      </div>
    </div>
  );
};

export default LimitUpMonitorPanel;
