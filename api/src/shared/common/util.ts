export const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const filterObjectColumnPublic = (
  columnPublish: string[],
  objectData: Record<string, any>,
): Record<string, any> => {
  const publishedData: Record<string, any> = columnPublish.reduce(
    (acc, key) => {
      acc[key] = objectData?.[key];
      return acc;
    },
    {},
  );
  return publishedData;
};
