import matplotlib.pyplot as plt
import logging


class GenPieChart:
    @staticmethod
    def generate_pie_chart(records):
        plt.rcParams["font.family"] = "AR PL UMing CN"
        plt.rcParams["axes.unicode_minus"] = False
        user_id = records[0]["user_id"] if records else None
        category_sums = dict()
        for record in records:
            if record["type"] == "收入":
                continue
            category = record["category"]
            amount = record["amount"]
            category_sums[category] = category_sums.get(category, 0) + amount

        labels = list(category_sums.keys())
        sizes = list(category_sums.values())

        plt.figure(figsize=(8, 8))
        plt.pie(
            sizes,
            labels=labels,
            autopct=lambda pct: f'{pct:.1f}%\n({int(pct/100.*sum(sizes))}元)',
            startangle=140,
            textprops={"fontsize": 16}
        )
        plt.title("支出分類佔比", fontsize=20)
        plt.axis("equal")
        plt.savefig(f"images/{user_id}.png")
