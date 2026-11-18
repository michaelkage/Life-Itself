import { useState, useEffect } from 'react';
import { Habit } from '../types';
import { getHabits } from '../lib/db';

export const useHabits = (userId: string) => {
  const [habits, setHabits] = useState<Habit[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHabits = async () => {
      setLoading(true);
      const data = await getHabits(userId);
      if (data) setHabits(data);
      setLoading(false);
    };
    fetchHabits();
  }, [userId]);

  return { habits, loading };
};
