import sys

def solve():
    """
    Reads grid dimensions, constraints, and grid from standard input 
    and calculates the maximum possible total score.
    """
    try:
        # Read N (rows)
        N = int(sys.stdin.readline())
        if not N: return

        # Read M (columns)
        M = int(sys.stdin.readline())

        # Read K (max allowed column index difference)
        K = int(sys.stdin.readline())

        # Read P (penalty constant)
        P = int(sys.stdin.readline())

        # Read the grid
        grid = []
        for _ in range(N):
            line = sys.stdin.readline().strip()
            if not line:
                break
            row = list(map(int, line.split()))
            grid.append(row)

    except EOFError:
        # Handle case where input might terminate early
        return
    except Exception:
        # General exception handling for robust execution in competitive environment
        return


    max_total_score = -float('inf')

    # Iterate over all possible minimum column indices L (Left boundary)
    for L in range(M):
        # The maximum allowed right boundary R must satisfy R - L <= K and R < M
        R_limit = min(M - 1, L + K)
        
        # Iterate over all possible maximum column indices R (Right boundary)
        for R in range(L, R_limit + 1):
            current_sum_of_selected_cells = 0
            
            # Calculate the maximum sum for this fixed column range [L, R]
            for i in range(N): # Iterate over rows
                row_max_in_range = -float('inf')
                
                # Find max grid[i][j] where L <= j <= R
                for j in range(L, R + 1):
                    if grid[i][j] > row_max_in_range:
                        row_max_in_range = grid[i][j]
                
                current_sum_of_selected_cells += row_max_in_range

            # Calculate Spread and Penalty
            spread = R - L
            penalty_value = P * spread
            
            # Calculate Total Score
            total_score = current_sum_of_selected_cells - penalty_value
            
            # Update maximum score found so far
            if total_score > max_total_score:
                max_total_score = total_score

    print(int(max_total_score))

if __name__ == "__main__":
    solve()