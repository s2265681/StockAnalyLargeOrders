import { render, screen } from '@testing-library/react';
import { SeatTable } from './index';

describe('DragonTiger SeatTable', () => {
  test('renders trader tag after the seat name', () => {
    const seatName = '东方财富证券股份有限公司拉萨东环路第二证券营业部';

    render(
      <SeatTable
        seats={[
          {
            seat_name: seatName,
            trader_tag: '拉萨天团',
            buy_amount: 12345678,
            sell_amount: 0,
            net_amount: 12345678,
          },
        ]}
      />
    );

    const seatCell = screen.getByTitle(seatName);
    const nameText = seatCell.querySelector('.dt-seat-name-text');
    const traderTag = seatCell.querySelector('.dt-seat-trader');

    expect(nameText.textContent).toBe(seatName);
    expect(traderTag.textContent).toBe('拉萨天团');
    expect(Array.from(seatCell.children)).toEqual([nameText, traderTag]);
  });
});
