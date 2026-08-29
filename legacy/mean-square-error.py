def calculate_mape(list1, list2):
    """
    Calculate the Mean Absolute Percentage Error (MAPE) between two lists.
    MAPE is used as a percentage-based measure of accuracy for continuous data.
    """
    if len(list1) != len(list2):
        raise ValueError("Both lists must have the same length")

    absolute_percentage_errors = [abs((x - y) / x) * 100 if x != 0 else 0 for x, y in zip(list1, list2)]
    mape = sum(absolute_percentage_errors) / len(list1)
    accuracy_percentage = 100 - mape  # Higher values mean higher accuracy
    return accuracy_percentage

if __name__ == "__main__":
    # Example lists
    list1 = [285, 178, 57]
    list2 = [254, 162, 57]
    list3 = [296, 194, 56]
    list4 = [238, 164, 56]
    list5 = [252, 168, 57]
    list6 = [260, 175, 57]

    try:
        accuracy2 = calculate_mape(list1, list2)
        accuracy3 = calculate_mape(list1, list3)
        accuracy4 = calculate_mape(list1, list4)
        accuracy5 = calculate_mape(list1, list5)
        accuracy6 = calculate_mape(list1, list6)

        print(f"Accuracy (List 2 compared to List 1): {accuracy2:.2f}%")
        print(f"Accuracy (List 3 compared to List 1): {accuracy3:.2f}%")
        print(f"Accuracy (List 4 compared to List 1): {accuracy4:.2f}%")
        print(f"Accuracy (List 5 compared to List 1): {accuracy5:.2f}%")
        print(f"Accuracy (List 6 compared to List 1): {accuracy6:.2f}%")
    except ValueError as e:
        print(f"Error: {e}")
