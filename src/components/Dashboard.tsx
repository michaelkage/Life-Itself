import React from 'react';
import { useHabits } from '../hooks/useHabits';
import { Card } from './Card';
import { Button } from './Button';

export const Dashboard: React.FC<{ userId: string }> = ({ userId }) => {
  const { habits, loading } = useHabits(userId);

  if (loading) return <div>Loading...</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Habits</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {habits.map((habit) => (
          <Card key={habit.id}>
            <h2 className="text-lg font-semibold">{habit.title}</h2>
            <p className="text-gray-600 mb-4">{habit.description}</p>
            <Button>Mark Done</Button>
          </Card>
        ))}
      </div>
    </div>
  );
};
