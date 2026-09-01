// *******************************************************************
//      file with specific functions to solve Knapsack problem
// *******************************************************************
#ifndef _PROBLEM_H
#define _PROBLEM_H

//----------------- DEFINITION OF PROBLEM SPECIFIC TYPES -----------------------

struct TProblemData
{
    int n;                                      // size of the RKO vector 

    // other variables of the problem at hand
    int nItems;                                 // number of items
    int cap;                                    // capacity of the knapsack
    std::vector <int> w;                        // weigth of the items
    std::vector <int> b;                        // prize of the items
};


//-------------------------- FUNCTIONS OF SPECIFIC PROBLEM --------------------------


/************************************************************************************
 Method: ReadData
 Description: read the input data
*************************************************************************************/
void ReadData(char name[], TProblemData &data)
{ 
    FILE *arq;
    arq = fopen(name,"r");

    if (arq == NULL)
    {
        printf("\nERROR: File (%s) not found!\n",name);
        getchar();
        exit(1);
    }

    // => read data
    int dummy = fscanf(arq, "%d", &data.nItems);
    dummy = fscanf(arq, "%d", &data.cap);
    
    //  weigth of items
    data.w.clear();
    data.w.resize(data.nItems);

    // prize of items
    data.b.clear();
    data.b.resize(data.nItems);

    for (int k=0; k<data.nItems; k++)
    {
        dummy = fscanf(arq, "%d", &data.b[k]);
        dummy = fscanf(arq, "%d", &data.w[k]);
    }
    
    // define the random-key vector size
    data.n = data.nItems;
}

/************************************************************************************
 Method: Decoder 
 Description: mapping the random-key solution into a problem solution
*************************************************************************************/
double Decoder(TSol &s, const TProblemData &data)
{   
    // create a solution of the KP
    std::vector <int> sol(data.n, 0);                        
    for (int i = 0; i < data.n; i++)
    {
        if (s.rk[i] > 0.5)
            sol[i] = 1;
    }

    // calculate the objective function value
    int cost = 0;
    int totalW = 0;
    for (int i = 0; i < data.n; i++)
    {
        if (sol[i] == 1)
        {
            cost += data.b[i];
            totalW += data.w[i];
        }
    }

    #define MAX(x,y) ((x)<(y) ? (y) : (x))

    // penalty infeasible solutions
    int infeasible = ((data.cap)<(totalW) ? (totalW - data.cap) : (0));
    cost = cost - (100000 * infeasible);

    // change to minimization problem
    cost = cost * -1;

    for ( const auto &cut : constraintPool){

        // Penalise solution accordingly
        double lhs = 0.0;
        for (int i = 0; i < data.n; ++i) {
            if(sol[i] == 1) lhs += sol[i] * cut.coeff[i];
        }
        double infeasibility = lhs - cut.rhs;
        cost += 100000 * (infeasibility > 0.0 ? infeasibility : 0.0);
    }

    return cost;
}


/************************************************************************************
 Method: Separate
 Description: Problem-specific separation method to generate violated cuts (d^T x <= rhs)
              Returns a set of violated cuts for the given solution.
              (To be implemented by the user for the specific problem)
*************************************************************************************/
std::vector<TConstr> Separate(const TSol &s, const TProblemData &data)
{
    // TODO: Implement the separation problem
    // return {};

    // Heuristic separation of cover inequalities for the relaxed knapsack problem
    // i.e., when variables are assumed as continuous. For exact separation, one
    // has to transform them to integer ones.
    std::vector<TConstr> cuts;
    std::vector ratios(data.n, std::tuple<int, double>{});

    for (int i = 0; i < data.n; i++) {
        ratios[i] = { i, (1.0 - s.rk[i]) / data.w[i] };
    }
    std::sort(ratios.begin(), ratios.end(), [](const auto &a, const auto &b) {
      return std::get<1>(a) < std::get<1>(b);
    });

    for (int i = 0; i < data.n; i++) {
        std::vector <int> cover;
        cover.reserve(data.n);

        // Add items within cover set by their benefit-cost ratio
        double sum_weights = 0.0;
        for (int j = i; j < data.n && sum_weights < data.cap; j++) {
            const auto [item, _] = ratios[j];
            sum_weights += data.w[item];
            cover.push_back(item);
        }

        // Check whether the built forms a violated cut, otherwise drop it
        double lhs = 0.0;
        TConstr cut { };
        cut.coeff.resize(data.n, 0.0);
        for (const int item : cover) {
            lhs += 1.0 - s.rk[item];
            cut.coeff[item] = 1.0;
        }

        // Violated cut of the form \sum_{j \in C} x_j \leq |C| - 1
        if (lhs < 1.0 - 1e-6) {
            cut.rhs = static_cast<double>(cover.size()) - 1.0;
            cuts.push_back(cut);
        }
    }

    printf("Separate returned %d cuts.\n", cuts.size());
    return cuts;
}

/************************************************************************************
 Method: FreeMemoryProblem
 Description: Free local memory allocate by Problem
*************************************************************************************/
void FreeMemoryProblem(TProblemData &data){
    data.b.clear();
    data.w.clear();
}

#endif