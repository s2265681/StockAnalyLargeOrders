import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LimitUpEchelon from './index';
import { apiRequest } from '../../config/api';

jest.mock('../../config/api', () => ({
  apiRequest: jest.fn(),
}));

const mockEchelonData = {
  summary: {
    total: 1,
    first_board_count: 0,
    consec_count: 1,
    max_boards: 2,
  },
  echelons: [
    {
      boards: 2,
      count: 1,
      stocks: [
        {
          code: '000001',
          name: '测试股票',
          seal_ratio: 5,
          first_time: '093000',
          break_count: 0,
          seal_amount_text: '1亿',
          turnover_text: '2亿',
          turnover_rate: 3.2,
          theme: '测试题材',
        },
      ],
    },
  ],
  theme_ranking: [],
  ai: { status: 'done' },
};

describe('LimitUpEchelon loading state', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    apiRequest.mockReset();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('keeps the loading indicator visible briefly when data resolves immediately', async () => {
    apiRequest.mockResolvedValueOnce({ data: mockEchelonData });

    const { container } = render(
      <MemoryRouter initialEntries={['/limit-up-echelon']}>
        <LimitUpEchelon />
      </MemoryRouter>
    );

    expect(container.querySelector('.loading-container')).not.toBeNull();
    expect(screen.getByText('加载涨停板梯队...')).not.toBeNull();

    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector('.loading-container')).not.toBeNull();
    expect(screen.getByText('加载涨停板梯队...')).not.toBeNull();

    await act(async () => {
      jest.runOnlyPendingTimers();
    });

    expect(container.querySelector('.loading-container')).toBeNull();
  });
});
